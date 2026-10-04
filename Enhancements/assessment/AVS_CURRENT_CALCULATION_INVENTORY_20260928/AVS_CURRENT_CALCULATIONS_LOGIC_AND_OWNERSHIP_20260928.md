# AVSHUNTER — Current calculations, logic and ownership

**Source assessment, 28 September 2026. Not a release approval.**

## 1. What this document is for

This is the verification agent's starting register of what AVSHUNTER currently computes, how the stages connect, what each number means and where to challenge it. It describes the working tree, not just the signed design or last commit. It does not change code, authorize trading, certify forecast accuracy, or claim that the outstanding TEV build is complete.

The business sequence remains:

```text
Dated market/database evidence
  → identify the underlying ticker's structure, direction and opportunity
  → preserve that ticker assessment
  → compare same-direction option expressions
  → assess contract economics, liquidity and current execution evidence
  → publish consistent Lab and Interpreter decision intelligence
  → human decision
  → record exact outcomes and learn without rewriting history
```

The intended ticker expectancy and exact-option expectancy are **different products**. An unsuitable option must not erase a good underlying thesis. Conversely, a good underlying move does not make every option profitable. Today's code still contains legacy calculations that mix those stages; the newer separation is not yet a complete numerical replacement.

Three separate verdicts are required for every calculation:

1. **Mathematically correct:** independently reproduces its stated formula, with valid units and boundary behaviour.
2. **Implemented to specification:** uses the agreed inputs, ownership, timing and downstream permissions.
3. **Predictively useful:** improves later, untouched outcomes after costs and with uncertainty accounted for.

A passing unit test, a fluent report, or a completed workflow cannot establish all three.

## 2. Snapshot, coverage and evidence limitations

Repository: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`.

Git HEAD read independently: `03fd4689534943daa61a46f0149f14d4e6f1be3e`. AST extraction ran **07:41:01–07:45:08 UTC on 28 September**. The accompanying summary records file hashes and a later change check. Source can change after this assessment; recheck hashes before using this as a release baseline.

Tracked local edits include Discovery, Wyckoff, fusion/enums, orchestrator, Morning finalizer, Lab backend/frontend, Interpreter structured projection and reference-input/archive tests. New TEV/domain/contract files also exist outside the committed baseline. Therefore **HEAD alone does not reproduce the assessed system**. Preserve an authorized working-tree release snapshot before verification.

### 2.1 Deliverables

| File | Contents and appropriate use |
|---|---|
| This document | Human-readable business calculations, owners, stage relationships, assumptions and verification priorities |
| `source_manifest.jsonl` | Each enumerated Python file, SHA-256, byte size, parse state and category |
| `function_register.jsonl` | Function/method name, containing scope, parameters, decorators, return annotation and source lines |
| `calculation_condition_register.jsonl` | Arithmetic, comparisons, Boolean combinations, conditional expressions and assertions, with source owner/lines |
| `dependency_call_register.jsonl` | Import statements and call expressions, including library calls used for calculations |
| `inventory_summary.json` | Counts, enumeration warnings, categories, hashes, verification change check and limitations |

Extraction found **1,344 readable Python files; 11,127 function definitions; 102,722 arithmetic/condition records; 10,115 import records; 143,842 call records**. These are syntax records, including nested expressions and repeated implementations—not distinct business formulas or production coverage counts.

The machine register deliberately includes tests/research/retained source copies in separate categories. A runtime candidate is **not** automatically an active owner. All string/bytes literals in extracted expressions are redacted to prevent accidental credential disclosure; source line references retain access to original field names and literals for an authorized reviewer.

**Limits:** `rg` enumeration reported ten access-denied warnings. Git ignores and explicit exclusions affect enumeration. Virtual environments, third-party dependency directories, data/run contents and `.git` are not recursively parsed. SQL text, PowerShell scheduling and HTML/JavaScript are not Python-AST formulas; their adapter behaviour is discussed here, but not certified by the AST register. Import paths, subprocesses and dynamic dispatch need runtime/fixture verification. No database content audit, provider request, pipeline run, current regression suite, or financial backtest was executed for this document. Parsing is not test passage.

Explicit attempts to inspect the latest run's descriptive forecast and EOD Interpreter directories encountered access restrictions during file discovery. Their current production adapter code is assessed; their inaccessible saved contents are not treated as inspected evidence.

### 2.2 Classification vocabulary

| Label | Meaning |
|---|---|
| LIVE CALL PATH | Invocation is visible in the inspected orchestrator/adapter; numerical coverage still requires evidence |
| SAVED RUN EVIDENCE | An inspected artifact proves a recorded result for one run, not all future runs |
| SUPPORT OWNER | Used by an inspected owner or adapter; exact execution may depend on inputs/configuration |
| PRESENT / REACHABILITY UNPROVED | Code exists, but this assessment has not proved that normal production calls it |
| LEGACY / DIAGNOSTIC | Older calculation or compatibility lane; do not confuse with the signed replacement |
| RESEARCH ONLY | Hypothetical/uncalibrated calculation without execution authority |
| DESIGN / NOT IMPLEMENTED | Requirement or proposed method, not current numerical behaviour |

## 3. Weekend changes that affect interpretation

### 3.1 Manifest and ledgers replace per-ticker packages

The 27 September commits implement P1–P4 of AVS-PKG-002: hashed input manifest, reference-mode Vanguard reads, per-run enrichment ledgers and package-free Evening. `run_vanguard_from_packages.py` retains its old name; that does not prove packages remain its input owner.

Consequences for verification:

- Join by run/session/ticker/dataset identity, not by whichever package JSON happens to exist.
- Verify actuarial/trap/trigger consumers use ledgers first; a residual `packages/*.json` glob can manufacture a false missing-data result.
- A file-count reduction and faster archive are storage changes, not proof of better trading calculations.
- Historical packages remain historical evidence; do not rewrite their meaning to match a new source convention.

The P1–P4 receipt records a P4b defect in the pre-EIL actuarial stamp, caused by a remaining package glob, and a subsequent uncommitted ledger-first repair. Its test counts are **receipt claims**, not tests rerun here. Inspect `inject_actuarial_into_superbrain_pre_eil` before release.

### 3.2 Latest inspected saved run: `20260927_205123`

| Recorded item | Inspected result |
|---|---|
| Terminal log | `EVENING WORKFLOW COMPLETE` at 28 Sep 01:21:07; the shared log also contains later test-fixture errors for other run IDs, which must not be attributed to this run |
| Discovery | 1,666 rows |
| Vanguard | 1,616 passed; 50 rejected with `DATA_FAILURE_NO_OHLCV` |
| Options / EIL / Execution | 1,550 rows each in final manifest |
| Morning | Pending; zero Morning validation rows |
| Technical / semantic health | Both `DEGRADED`; health score 92 |
| Selected-handoff missing invalidation | Final manifest 118; EV-3's narrower directional-selected population 117 |
| EV-3 applicable / evaluated | 1,337 / **0** |
| EV-3 top row reasons | 852 no-evaluable-contract, 436 horizon, 49 thesis-price; 213 non-applicable rows |
| EV-3 calibration | `INSUFFICIENT_OUTCOMES`; no capital authority |
| Completed market profile | Final manifest `FAIL`, zero rows |
| Macro ticker context | Manifest packet `AVAILABLE`, but row diagnostics: 1,405 stale and 145 conflicting; zero available row contexts |
| Run permission | `MORNING_VALIDATION_REQUIRED`; `run_tradeable=false` |

The 118-versus-117 counts use different populations. Reconcile identities before calling this a duplicate-count defect. Similarly, an available parent macro packet does not make all of its ticker evidence fresh.

Sources: `final_run_manifest.json`, `vanguard/vanguard_run_summary.json`, `ev3_shadow/ev3_shadow_phase_status_20260927_205123.json`, the shared orchestrator log and P1–P4 receipt. Completion is **workflow completion**, not a claim that EV or all evidence is functional.

### 3.3 New plan is not implemented behaviour

`AVS_TEV001_BUILD_PLAN_20260927.md` documents eleven incomplete stages, a proposed simplification using existing C12 owners, duplicate engines, research-EV concerns and advisory publishers currently capable of aborting Evening. It proposes flagging/decoupling work. Do not assume those flags or retirements have happened simply because the plan says they should.

The inspected orchestrator currently calls descriptive C5 after Vanguard, then Options, then C6/C8. GARCH/Q-OMEGA and empirical-EV shadow publication occur later. Thus the early C5 packet is **not automatically a numerical synthesis of all later-enriched evidence**.

## 4. Units and identities that every stage must preserve

| Quantity | Required interpretation / current risk |
|---|---|
| Underlying price, strike, premium | USD; premium normally USD per share. Contract dollars require the actual multiplier |
| Probability | Fraction 0–1; legacy Vanguard CSV win rates sometimes use 0–100 and adapters normalize by column family |
| Return | Fraction unless explicitly `_pct`; 0.10 and 10.0 are not interchangeable |
| Annual volatility / IV | Fraction; annual vol 0.30 means 30%. Not a probability of direction |
| Expected move | Canonical `expected_move_*d_fraction` cumulative one-sigma move in XNYS sessions; legacy incremental display percentages have a different clock |
| Delta | Signed for puts in quote models; some legacy economics explicitly uses absolute delta |
| Gamma | Option-price sensitivity per underlying-dollar squared; multiplier and GEX dollar scaling are separate |
| Theta / vega | Provider conventions must be retained; daily theta versus annual theta and vega per vol point versus vol fraction cannot be guessed |
| Spread | Shared long-option owner uses `(ask−bid)/mid`; percentage display is 100 times that fraction |
| Horizon | Anticipated move window, permitted holding window, actual first-passage time and expiry/runway are different clocks |
| Timestamp | Evidence session, provider observation, acquisition, publication and report cut-off are distinct |
| Identity | Ticker/security identity; exact OCC symbol/right/strike/expiry/multiplier; run and source dataset IDs; content hash |

Cross-stage unknowns must stay unknown. A synthetic price, a default confidence of 50, a zero substituted for missing Greeks, or an expiry payoff cannot silently become measured current evidence.

## 5. Data and history owners

The business may describe two main databases (historical/actuarial and Phantom), but code additionally uses canonical price/chain storage, a dataset registry, replay caches and decision/outcome ledgers. They do not contain interchangeable evidence.

| Owner | Supplies | Calculations / downstream role | Verification obligation |
|---|---|---|---|
| Canonical daily prices | Dated OHLCV plus ingestion and revision history | Discovery, volatility, relative paths, C12 universe | Reconstruct values available by cut-off, adjustment convention, gaps and security changes |
| Actuarial historical state cache | Feature buckets and 5/10/20-session forward fields | Vanguard match ladder, return quantiles, momentum transitions | Historical feature version must match live feature version; exclude future information at decision time |
| Phantom / option history | Exact chain observations, Greeks/IV history and related evidence | Quote history, IV surface/rank, contract outcomes | Exact symbol and quote date; duplicate/provider/Greek coverage; no nearest-date substitution disguised as exact |
| Canonical chain registry | Dataset identity, content hash, schema and observation lineage | C6, DOI and exact-contract joins | Cached same-session dataset may originate in another run; preserve original lineage while recording current run's link |
| EV-3 barrier sidecar | State/direction/horizon/target-stop grid cells | Legacy EV-3 probabilities and exit timing | Match distance and support, cache version, clocks and held-out calibration |
| Run manifest / ledgers | Frozen input references and stage enrichments | Vanguard, EIL, Lab and Interpreter | One run-scoped owner; stale legacy package reads must not override ledger truth |
| C12 / DOI / journal ledgers | Immutable decisions, observations, labels and counterfactual scope | Learning, probability acceptance, ranking evaluation | Censoring, available-case coverage, costs, selections and rejected/missed candidates |

`canonical_data/forecast_path_reader.py` uses `ohlcv_daily`, `ohlcv_daily_revisions` and `ohlcv_ingest_batches`, opening SQLite read-only. It reconstructs past rows rather than assuming the latest corrected bar existed then. The research path lane instead explicitly reads **current-known history**. That difference affects what can be claimed from a simulation.

No new claim about database completeness or size is made here. A database existing does not prove the required version-equivalent feature/outcome join exists.

## 6. End-to-end calculation and rule register

The IDs below are business calculation groups. The machine annex contains finer source expressions and calls. Formulas here describe code, including questionable formulas; they are not endorsements.

### 6.0 Macro normalization, regime, sector and money-context calculations

Owners: `scripts/normalise_macro_contract.py`, `scripts/macro_quant_packet.py`, `contracts/macro_regime_safety.py`, `macro_domain/us_money_index.py`, `domain/macro_advisory_context.py` and `scripts/sector_alignment.py`. The orchestrator visibly builds/refreshes the packet, invokes normalization and attaches the USMI sidecar. Individual legacy helpers do not automatically have decision authority.

| ID | Current calculation/rule | Outputs, limitations and downstream meaning |
|---|---|---|
| MC01 | Net-liquidity fallback: label mapping .80/.62/.50/.38/.22; otherwise `clip((4-week delta in USD billions+200)/400,0,1)` | Preserves supplied authoritative structured scores. Label fallback is an ordinal transform, not a measured probability; a missing delta remains absent |
| MC02 | VIX fallback `clip(1-(VIX-12)/(40-12),0,1)` | Higher score means lower fear, not higher expected ticker profit. At VIX26, score=.50 |
| MC03 | GEX fallback `clip((net GEX+5e9)/1e10,0,1)`; positive/dampening label=.70, negative/amplifying=.30 | Requires aggregate units/sign conventions. Contrary to its stale docstring, executable no-data branch returns `None`, not neutral .50 |
| MC04 | Conviction above1 divided by100, then clipped0–1; otherwise retained | A producer's conviction is not independently calibrated. Several fallback chains use Python `or`, so valid zero can be treated as absent; test this explicitly |
| MC05 | Regime distribution is a fixed lookup: e.g. TRENDING_BULL=.75/.20/.05; TRANSITIONAL_BULLISH=.45/.35/.20; TRANSITIONAL_NEUTRAL=.30/.40/.30 | Ordered bull/neutral/bear. These sum to1 but are policy priors, not empirical ticker probabilities. Transitional sub-state uses drift/bias strings and conviction .55; explicit neutral drift takes precedence |
| MC06 | Risk score from text: +55 risk-on,+10 selective,−25 no-go,−65 risk-off,−100 crisis; transitional/choppy upper cap25; final clamp−100..100 | Multiple strings can contribute simultaneously. No probability interpretation; compare raw label, sub-state and reduced packet regime |
| MC07 | Packet age `(now-as_of)/3600`, rounded2 decimals; FRESH≤20h, STALE≤72h, otherwise EXPIRED; missing time=MISSING | Uses as-of/generated/report-date priority, not normalization time. Negative age currently satisfies FRESH in this helper; temporal-truth owners must reject future evidence rather than trusting that label alone |
| MC08 | Core conflicting regime/risk-switch values→CONFLICTED freshness/quality; active conflict flags→PARTIAL; otherwise CONFIRMED | Resolved merge notes separated from active conflicts. CONFIRMED here is a conflict-status rule, not proof that every economic series is populated or correct |
| MC09 | Liquidity pulse from labels or score≥.6 expanding/≤.4 contracting; gamma analog .6/.4; VIX curve ratio beyond ±.05 gives contango/backwardation | Provider VIX-curve unit must be checked. Vol labels additionally use VIX16/25 and contango+VIX<18. Classification is not a money-flow measurement |
| MC10 | Credit risk75 tightening/25 easing/50 otherwise; sector tilt=`clip(50+10×(preferred count−avoid count),0,100)` | Missing credit becomes neutral-like50; sector-list count does not measure how much capital moved. Preserve evidence state beside values |
| MC11 | Bucket clarity: equities=`clip(50+risk/2,0,100)`; bonds65 if easing else45; USD65 if strengthening else45; credit100−risk; commodities60 if text mentions GOLD/COMMOD else45; largest becomes primary bucket | Description matching is not measured transmission. `liquidity_score` parameter is not used by this helper; do not attribute a liquidity-derived clarity estimate to it |
| MC12 | Equity-drawer warning if≥3 of rates-up/USD-up/tightening-credit/risk<−30; cautions also include freshness/data conflict and confidence<.4 | Advisory caution, not independent order permission |
| MC13 | Quant-packet ticker alignment: first present sector field matched by substring against preferred/avoid lists→ALIGNED100/CONFLICTED0/NEUTRAL50; absent→UNKNOWN0 | Does not validate ETF constituents or adjust alignment to ticker direction. The0 for missing must not become bearish measured evidence. Contrasts with directional USMI route rules |
| MC14 | USMI structured scenarios: evaluate all numeric `gt/lt/gte/lte` predicates; missing/unsupported predicate stays unavailable; one match selected, several=MULTIPLE_MATCH, none uses configured default | `ADVISORY_ONLY`; retains per-predicate results. A default scenario is not confirmation that its conditions were observed |
| MC15 | USMI sector/direction/industry routing uses canonical categories, industry overrides and source route priority; exposes routing version/reason | Distinguish `usmi_routing_key` (descriptive key) from actual route lookup; broad technology is not silently semiconductors in canonical `sector_advisory` |
| MC16 | Legacy sector multiplier: tailwind1.10, neutral1, mixed.80, headwind.55, unknown.80; HEADWIND+RISK_OFF emits `SECTOR_RISK_OFF_BLOCK`, otherwise reduction | Present helper returns block/size language; orchestrator loading does not prove final decision consumes that authority. Old .80 conviction-block comment/constant is not actual branch. Verify display-only governance at every consumer |
| MC17 | Packet canonical JSON SHA-256/source-byte fingerprint; merge fills missing fields, retains committed values and records old/new conflicts | Identity/immutability logic, not a market score. Flattens named macro fields into row columns for downstream Lab/Interpreter joins |

Economic actual-versus-forecast, USD/JPY changes, bond scores and other source metrics are often **accepted inputs** rather than recomputed in the quant-packet helper. Their field presence is not proof of an independently calculated surprise or measured capital flow. The full source register also covers bond/event/catalyst companions; numerical certification must trace their raw series, timestamp and actual invoked owner separately.

### 6.1 Scanner: opportunity hints before the core pipeline

Owner: `scripts/avshunter_universe_scanner.py`. The user can run it separately; its scanner hints must not become an alternative governing ticker-direction authority.

| ID | Current computation / logic | Outputs and downstream effect |
|---|---|---|
| SC01 | Price history computes momentum, MA position, RSI, realised vol, ATR/compression context | Scanner VMS and direction votes |
| SC02 | ATM IV is mean IV of ten strikes nearest spot; historical IV rank `(IV−min)/(max−min)`; constant range fallback 0.5 | `iv`, `iv_rank`, source/confidence labels |
| SC03 | If real IV history is too thin, IV rank uses RV×1.2 history proxy, with confidence 0.65 rather than 0.95 | Synthetic source must remain visible; not measured IV history |
| SC04 | Term slope = mean IV DTE<14 minus mean IV DTE>30; skew = mean put IV−mean call IV; missing branch substitutes 0 | Score can receive apparently neutral inputs when term/skew is missing; verify evidence labels |
| SC05 | VMS: IV rank <.3 adds20, >.7 adds0, otherwise10; RV>IV adds25; compression20; term slope≥0 adds15 else10; abs(skew)<.05 adds20, positive skew10 else5 | 0–100 heuristic; GO/PROBE/WAIT/BLOCK thresholds, not calibrated EV |
| SC06 | Direction votes: ±20d momentum, MA20/MA50 sides, RSI extremes, skew and compression; tied votes→NEUTRAL | Scanner CALL/PUT is a hint, not the signed underlying forecast |
| SC07 | Sector-relative strength, dark-pool proxy, ETF-relative options-volume flow, Form4 context and lead-signal score | LSS and lead context; proxy labels must not claim measured hidden orders |
| SC08 | Contract subscores VMI/DC/CFS/PG/MM plus pre-screen and long-contract scoring | Scanner contract hints; separate from downstream canonical C6/DOI candidate search |
| SC09 | Short/borrow adapter has an unavailable path; evidence guards may downgrade incomplete lead rows | Distinguish missing provider capability from bearish information |

Scanner's hard-coded ETF map and the governed universe map are separate code locations. Do not modify the universe during this assessment; verify source precedence and map lineage. A price-return relative-strength metric is not proof of cash inflow into that ticker.

### 6.2 Discovery: indicators, structure and compression

Owners: `avshunter_discovery_ULTIMATE.py`, `WyckoffEngine_3101_v2.py`, precursor logic, `enums_structural.py`, `swing_fusion.py`, asymmetry gate and database feature builders.

| ID | Current formula / rule | Meaning and consequence |
|---|---|---|
| DS01 | True range `max(H−L, abs(H−prevC), abs(L−prevC))`; ATR/BB/ADX/RSI/momentum/volume features in their owners | Not every field called ATR uses the same averaging method; preserve method/version |
| DS02 | Wyckoff local range: scan recent ten bars for first high>prior20-high×1.02 or low<prior20-low×.98; anchor range before event, requiring at least ten prior bars | Weekend fix avoids testing a break against a range containing its own break bar |
| DS03 | Range width `(range_high−range_low)/mean(close)`; boundary touches near 98% high and 102% low; break/reclaim counts | Evidence features, not calibrated likelihoods |
| DS04 | Absorption count from volume ratio>1.5 and spread ratio<.8; SOT = mean TR(last10)/mean TR(previous10), denominator floor .001 | High effort/low result and thrust-shorting proxies |
| DS05 | Buyer/seller scores from absorption closing position, failed breakdown reclaims×3, follow-through failures and mean closing position | BUYERS if difference>3, SELLERS if<−3, EQUILIBRIUM if abs≤1, otherwise SHIFTING |
| DS06 | Independent phase A–E scoring and event scoring; engine may emit UNKNOWN rather than force a weak phase | Per-phase rules are fully located in function/condition annex; phase scores are not probability estimates |
| DS07 | Phase confidence =35+clamp(chosen−best_other,0,50); UNKNOWN capped35 from half strongest raw evidence | Heuristic separation confidence; not an observed 85% accuracy claim |
| DS08 | Composite Wyckoff score `.35 phase_evidence + .35 event_evidence + .30 control_confidence` | 0–100 structural quality |
| DS09 | Truth confidence `clamp(.6 phase_evidence+.4 event_evidence−10×contradictions,0,100)` | Repeated correlated contradictions may double-tax the same input; audit lineage |
| DS10 | Next-phase hint if adjacent score>.8 current score; otherwise stable; UNKNOWN gets best-score hint at25 confidence | Not a learned longitudinal episode transition model |
| DS11 | Operator: A/B/C plus buyer control→accumulation; seller→distribution; D/E→markup/markdown by control; otherwise unclear | Mode and phase are distinct. Accumulation can persist; changes must be observed, not scheduled |
| DS12 | Legacy levels: long stop recent20-low×.98; target recent20-high×1.05; short stop high×1.02; target low×.95 | Rule-based geometry; not an estimated distribution of reachable moves |
| DS13 | Crabel compression =mean(H−L,7)/mean(H−L,20) | Uses high-low ranges, not full true-range ATR, despite internal `atr7/atr20` names |
| DS14 | Crabel own-history rank =share of last60 compression observations strictly below current; volume dryness rank analogous; short history defaults rank50 | Comment says universe-relative but implementation is ticker-own-history relative |
| DS15 | Crabel base65; NR7+volume ratio<.8→90; NR7→75; extreme→85; rank<15 adds10 or <25 adds5; cap100 | READY/COILING/NONE/DATA_INSUFFICIENT typed result; complete remaining branches in annex |
| DS16 | Discovery composite `.6 Wyckoff + .4 Crabel` when Crabel>0, otherwise Wyckoff only | Complementary scoring, but fusion still contains explicit gates |
| DS17 | Discovery `calculate_win_probability`: clamp(40+.25 composite,35,75) | Percentage-scale heuristic called a probability. No empirical calibration is supplied by this formula |
| DS18 | Tier from configured composite thresholds; late-trend prior adjustment remains; macro tier adjustments retired | Tier is priority/quality classification, not execution permission |
| DS19 | Fusion direction LONG for BUYERS+long operator, SHORT for SELLERS+short operator, otherwise NONE | This rule still leaves unresolved direction in some states; do not claim new scenario prediction has replaced it |
| DS20 | Fusion alignment base50, +20 compatible phase/compression, +10 control agreement, −30 UNKNOWN, −20 if≥2 contradictions; clamp0–100 | Missing compression gives no synergy bonus rather than a directional reversal |
| DS21 | Fusion intent OBSERVE_ONLY if alignment<50, phase UNKNOWN, evidence<30 or direction NONE; weak range with no compression may TRANSITION | Existing deterministic gate behaviour; tension with requested predictive composer must be assessed, not hidden |
| DS22 | Asymmetry/structural trigger and sourced stop validation; selected direction mapped to existing CALL/PUT fields | Current legacy ticker schema still uses option vocabulary; C5 converts to BULL/BEAR |

Important handoff risk: typed `crabel_result['state']` is consumed by fusion, while C5 reads the published `crabel_state`. Previously stored rows had blanks because early-position/precursor publication differed. A passing fusion test is not proof of CSV→C5 parity. `wyckoff_mode_phase_key` similarly does not prove the actuarial matcher uses it.

### 6.3 Vanguard Layer 1: auction context

Owners: `vanguard/layer1_auction/{market_profile,value_acceptance,value_migration,control_identifier,auction_synthesizer}.py`; completed-profile integration and manifest adapter.

| ID | Current method | Output / limitation |
|---|---|---|
| VG101 | TPO distribution increments each price level touched by each bar, price grid $0.10 | Time-at-price proxy, **not** transaction volume-at-price despite some comments |
| VG102 | POC =price with max TPO count; value area expands around POC to configured 70% count | POC/VAH/VAL, profile shape and balance |
| VG103 | Value acceptance, rejection and migration compare price/profile placement and profile movement | Acceptance/migration scores into auction verdict and historical fingerprint |
| VG104 | T&S aggression: buy-at-ask / sell-at-bid size proportions when supplied | Directly observed only if valid T&S exists |
| VG105 | Without T&S, green/red bar volumes estimate aggression; absent bars return unknown/balanced defaults | Must display HTF/profile proxy, not observed order-book control |
| VG106 | Aggression, efficiency and volume trend synthesize controller/confidence; auction rules combine with profile | BUYERS/SELLERS/BALANCED and auction states can affect legacy Layer2 gates |

The latest manifest shows no completed-profile rows. That must not be described as measured real-time control. Positional strategies bypass a legacy zero-intraday penalty; bypassing a penalty does not create missing intraday evidence.

### 6.4 Vanguard Layer 2: state matching and statistical outputs

Owners: `vanguard/layer2_statistical/{state_calculator,actuarial_query,edge_detector,scenario_builder}.py`; actuarial cache and enrichment ledgers.

| ID | Current computation | Downstream relationship |
|---|---|---|
| VG201 | DB-consistent vol state: ATR%=14-span EWM TR/C×100; BB width=4×rolling20 std/mean×100; ranks against last252 context | COMPRESSION if both ranks<30; EXPANSION if either>70; otherwise NORMAL |
| VG202 | State vector/hash includes volatility, trend maturity, structure, positioning, catalysts and bucket dimensions | Actual matching dimensions/fallback stage must be published; broad legacy phase remains a version risk |
| VG203 | Match ladder: exact/relaxed/fallback similarity and horizon-specific sample rules | High sample size on a coarse fallback is not exact-pattern evidence |
| VG204 | Historical forward returns produce means, conditional gains/losses, directional frequencies, p01…p99 quantiles and observation counts by horizon | Underlying statistics, not exact-option returns |
| VG205 | Target/drawdown probabilities and match-confidence weighting/calibration attrs | Distinguish fitted/calibrated evidence from a policy confidence haircut |
| VG206 | Forward momentum confidence =fraction future bucket rank>current, or momentum_delta>0 fallback | CONTINUATION/TRANSITION and momentum-tier context |
| VG207 | Intraday context may adjust scalar outcomes; full return quantiles are carried through without scalar rescaling | Means/frequencies and quantile distribution may have different adjustment bases |
| VG208 | Edge gates: conflicted auction, weak statistical confidence, trend exhaustion, options viability, EV floor and other quality rules | **Legacy ticker edge assessment still consults options viability**, contrary to clean two-stage separation |
| VG209 | Gate5 uses underlying actuarial EV as `net_ev`; EV2 is additional diagnostic, not primary; equity trading-cost subtraction removed | Source units and side correctness need explicit reference checks |
| VG210 | Direction evidence scores auction ±40confidence, migration ±30/15, directional probability ±20 and trend ±10 | CALL/PUT recommendation; legacy fallback can default CALL when evidence ties/no trend |
| VG211 | Right-side score starts50, adds structure/control/migration/probability/trend and context bonuses | Weighted confidence score; not an independently validated win probability |

The actuarial cache contains information beyond own pipeline run starts. A support conclusion based only on four run sessions or 195 own starts does not establish that the entire canonical universe is unusable. Conversely, large database row counts do not prove independence, PIT integrity or equivalent features.

### 6.5 Vanguard Layer 3 and Q-OMEGA volatility

Vanguard trade-plan owners build scenarios, invalidation criteria, execution gates, recommended horizon and confidence. The separate root `layer3_forward_variance.py`/GARCH runner forecasts volatility; do not conflate two modules both called Layer3.

| ID | Current formula / logic | Interpretation |
|---|---|---|
| VOL01 | Returns; squared daily returns as realised-variance proxy; price-history break truncation | Not intraday realised variance; corporate-action/security-reuse guards matter |
| VOL02 | HAR primary OLS: next squared return =a+b1 lag1+b5 mean5+b22 mean22; `n_fit=min(180,len(rv)-23)`, target slice starts at index23 | For longer supplied histories this takes the early capped fit slice, not automatically the most recent180 observations. Predictor/target alignment and intended training dates require independent check |
| VOL03 | HAR daily variance floored at half last5 mean squared returns; horizon average decays toward last60 mean at `.92^h` | Policy additions, not a learned full joint return path distribution |
| VOL04 | Annual vol `sqrt(mean forecast daily variance)×sqrt(252)`; GARCH(1,1) fallback with percentage-return conversion | GARCH coefficients are not HAR coefficients; method label must reflect actual path |
| VOL05 | EWMA `v=.94v+.06r²`; ATR proxy `mean(TR)/lastC/1.25×sqrt252` | Fallbacks with distinct assumptions/support |
| VOL06 | Governed annual vol floor.05/cap2.5; retain raw value and clipped state | Range guard, not evidence of predictive improvement |
| VOL07 | Jump flag short5 sample vol/long20 sample vol≥1.5; flat/short history returns unassessed | Missing must not become jump=false/safe |
| VOL08 | Confidence `.40 bars_score+.35 stability_score+.25 method_score`; bars capped at252; stability from rolling20 vol CV | Heuristic confidence; method scores HAR100/GARCH90/EWMA65/ATR35 |
| VOL09 | Legacy expected move `% = annual_vol×sqrt((calendar_days×5/7)/252)×100`; publishes 5, 10−5 and 20−10 increments | **Calendar-day incremental representation** retained for legacy display |
| VOL10 | Canonical budget fraction `annual_vol×approved_bias_multiplier×sqrt(hold_sessions/252)` | **Cumulative XNYS-session representation**; hold validated1…20 |
| VOL11 | Bias multiplier only applied with approved flag, VALIDATED state, held-out pass and report ID | Current config unvalidated, multiplier1.0 unapplied |
| VOL12 | `cumulative_expected_move_pct` prefers canonical fraction×100; conflicting convention→None; legacy complete increments summed | No shorter-horizon fallback. However legacy sum retains old calendar clock; it is not numerically identical to VOL10 |
| VOL13 | IV tailwind/RIEG signed `implied_vol−forecast_vol` | Negative means cheaper implied vol for buyer; not bullish ticker direction |

No volatility band establishes that a target is probable, reachable before invalidation, or profitable after option decay. Clock conversion and label ownership remain verification priorities even after H1/H2 repairs.

### 6.6 Options Intelligence: chain, Greeks, positioning and selection

Owner: `scripts/avshunter_options_intelligence.py`, canonical chain/identity adapters, IV history, Heston helpers, liquidity/ticket-spread policy and DOI services.

| ID | Current computation / rule | Outputs / effect |
|---|---|---|
| OI01 | Chain normalization, OCC/root/right/expiry/strike identity, quote flags and provider lineage | Invalid/crossed observations retained for audit, excluded from selection |
| OI02 | BS d1/d2, call/put value; delta/gamma/theta/vega; numerical implied-vol solve | Model-derived Greeks must remain distinct from provider observations |
| OI03 | Heston characteristic-function integration, calibration/proxy and numerical Greeks | Additional model-mark path; no implied proof of better forecasting |
| OI04 | IV percentile empirical CDF; IV rank `(IV−min)/(max−min)`; insufficient/flat history→missing | Percentile, rank and absolute IV are different quantities |
| OI05 | IV ownership: own IV history priority, explicitly labelled realised-vol proxy, provider per-contract source, unavailable | Proxy cannot silently become true historical IV rank |
| OI06 | Put/call OI and volume ratios, delta-weighted OI, OI walls, gamma islands, volume anomalies, gamma velocity | Positioning proxies; calls-positive/puts-negative is an assumption, not measured dealer inventory |
| OI07 | OI gamma flip reprices chain over spot grid: sum(sign×gamma×OI×spot); nearest crossing | No crossing→missing, not arbitrary fallback strike |
| OI08 | Macro GEX dollar exposure sum(sign×gamma×OI×multiplier×S²×.01); repriced crossings | Different exposure scale/grid from OI flip; normalize before treating sources as conflicting |
| OI09 | Sector-relative price evidence from canonical closes; volume confirmation and volume-quality indicators | Sector attribution must use correct mapping and cut-off |
| OI10 | Legacy best-contract selector: same right, holdable DTE, absolute delta mandate, valid mark, usable two-sided spread; scores delta/theta/vega/liquidity/DTE | A single pre-selected contract still exists beside multi-candidate TEV/DOI lanes |
| OI11 | Alternate/repair contracts, debit-vertical helper and stand-down/research route | Presence does not mean authority for every strategy; v1 signed scope must govern |
| OI12 | OIS grouped score: vol22, structure22, economics22, microstructure22, volume/momentum12; sample penalty−15/−10/−5 below50/100/200 | 0–100 heuristic with positive/negative reasons; not calibrated expected return |
| OI13 | Contract multiplier inference only under qualified standard-OCC provenance | Many older economics helpers still multiply by100 directly; adjusted contracts need checking |

Standard BS owner formula (with each owner's dividend convention):

```text
d1 = [ln(S/K)+(r−q+σ²/2)T] / (σ sqrt(T)); d2=d1−σ sqrt(T)
CALL = S exp(−qT) N(d1) − K exp(−rT) N(d2)
PUT  = K exp(−rT) N(−d2) − S exp(−qT) N(−d1)
```

American pricing, finite differences, expiry handling, dividend materiality and Greek unit scaling must be checked per owner; not every pricer uses this same model. A theoretical price is not an executable bid.

### 6.7 Legacy trade economics and mispricing

| ID / owner | Actual formula | Why the distinction matters |
|---|---|---|
| EC01 OI trade economics | CALL expiry BE=K+mark; PUT=K−mark | Expiry breakeven is not a pre-expiry holding-period breakeven |
| EC02 OI | At structural target intrinsic =max(T−K,0) CALL or max(K−T,0) PUT; gain=intrinsic−mark; `rr_options=gain/mark` | Target-intrinsic return proxy, not a first-passage/friction-adjusted EV |
| EC03 OI | `max_convex_r_multiple=intrinsic/mark`; `rr_premium_expected=rr_options` | Payoff multiple and net return differ by one when fully valued this way |
| EC04 OI | `ev_ratio=[p×gain−(1−p)×mark]/mark`; cheap IV factor1.15, expensive .75 | Binary heuristic option EV; p comes from upstream percentage, not necessarily calibrated option-profit probability |
| EC05 OI | Theta drag%=abs(theta)×hold/mark×100; IV-crush estimate from vega×.10×100 divided by mark×100 | Check whether .10 means fractional vol shock or ten vol points under actual vega convention |
| EC06 Layer4 | RIEG=IV−forecast; edge_gap%=expected_move%−breakeven% | Differences, not expected value by themselves |
| EC07 Layer4 | CCR=`premium×max(move−BE,0)/BE / [premium+abs(theta)hold+.5premium spread_fraction]` | Carry/payoff heuristic, not repriced exact contract |
| EC08 Layer4 | Win payoff=`premium×.5×edge_gap/max(edge_gap,.01)` if gap>0; EV=`[p win_payoff−(1−p)(premium+theta_drag)]/premium` | For positive gap≥.01 payoff is always half premium: destroys most sensitivity to move magnitude; docstring differs from actual code |
| EC09 Layer4 | Mispricing score =.30×RIEG transform+.25×gap transform+.25×CCR transform+.20×surface transform±3 term modifier; clamp0–100 | Heuristic score; cheap≥60, expensive≤40 |
| EC10 Layer4 | Convexity value=CCR component max50+gap max30+RIEG max20 | Distinct from eight-condition convexity count and gamma itself |

Do not rename EC02/EC04/EC08 as the agreed replacement EV. Trace whether each field is actually consumed by gates/rank/display in the current path before deciding its severity.

### 6.8 EV2: multiple copies and compounded heuristics

Owners present: root `ev_engine_v2.py` (header v2.2), `vanguard/ev_engine_v2.py` (header v2.1), `vanguard/ev_engine.py`, plus script helpers. EIL manipulates `sys.path`, so basename imports require explicit resolution verification. The register preserves all copies; it does not bless them as simultaneous authorities.

For the inspected Vanguard EV2 copy:

```text
p = clamp(.55 actuarial_hit_rate + .45 quality_blend, .05, .95)
quality_blend=.40 predictability/100+.25 BMPS/100+.20 calibration/100+.15 flow/5
structural_EV=p×expected_move+(1−p)×loss_move
path_adjusted_EV=structural_EV×path_multiplier
winning_option_proxy=(abs(move)×delta×S+.5 gamma×(move×S)^2)/premium
contract_EV=p×winning_option_proxy+(1−p)×loss_proxy−theta_cost+vega_adjustment
contract_efficiency=clamp(contract_EV/abs(structural_EV),.3,1.3)
final_EV=path_adjusted_EV×contract_efficiency×execution_multiplier×regime_multiplier×convexity_boost−runway_penalty
confidence_adjusted_EV=final_EV×confidence_multiplier
```

Defaults/fallbacks include actuarial rate.4 when all supplied rates are zero, premium floors/defaults, delta.4, gamma.02, theta.01, data-quality/confidence defaults and DTE-derived horizon5/10/20. Zero used as “absent” through `or` chains may replace a legitimate measured zero.

Other EV2 pieces:

- Path multiplier blends survival×1.2 and `.8+.4 path_cleanliness`, subtracts `.4 gamma_obstruction`, clamp.4…1.5.
- Theta cost clamp(theta×horizon×1.15 if short DTE / premium,0,.8); vega adjustment is a capped score transform, not a path repricing.
- Execution multiplier taxes spread, drift, IV distortion and slippage, clamp.5…1.
- Runway penalty is stepwise .50/.25/.12/.05/0.
- Confidence multiplier averages data quality and calibration scales, clamp.25…1.
- Convexity boost rewards transition, squeeze, cheap IV/tailwind and high convexity; cap1.6.
- Hard gates: failed breakeven, zero runway, spread>.30, no price; blocked EV set−1.
- Status bands at .25/.10/0/−.10 produce PASS_HIGH/PASS/PASS_SMALL/WEAK_PASS/FAIL and legacy size hints.

The Vanguard copy's regime multiplier returns1.00 with display-only rationale. Root v2.2's header and signal-tier features differ; a full equality/import-resolution fixture is required. These composed scores are **not clean ticker EV plus exact-option EV**, nor a certified risk bound.

### 6.9 EV3: barrier cache and exact-contract diagnostic

Owners: `vanguard/ev3_stage0.py`, `vanguard/ev_engine_v3.py`, shadow-phase/policy scripts and authority adapter.

| ID | Current computation / rule | Output / consequence |
|---|---|---|
| EV301 | Validate direction, side-correct target/stop, quotes/identity/Greek units/liquidity, state and clocks | Typed rejection before any EV |
| EV302 | **Requires hold exactly5/10/20 for horizon bucket1_5D/6_10D/11_20D** | Known anticipated-move-versus-hold mismatch remains in current source; zero coverage must not be called a functioning replacement |
| EV303 | Barrier sidecar estimates p_target_first, p_stop_first, p_timeout and exit-session statistics on state/grid | Coarse geometry/state matching and effective support need checks |
| EV304 | American option pricing, anchored to entry quote, exit friction and IV base/stress | Target/stop exit at level; timeout uses entry spot in this implementation, not full survivor-return distribution |
| EV305 | `EV_base=sum(p_j R_base,j)`; stress analogous; conservative=min(base,stress) | Three-scenario physical-probability mixture |
| EV306 | Probability uncertainty=z×sqrt(weighted outcome variance/n_effective); add model, spread, quote-age, default, state-fallback and exit-time-default penalties | `lower_bound=conservative_EV−sum(penalties)` is a model/policy bound, not independently proven statistical coverage |
| EV307 | Negative/indeterminate/positive-unvalidated bands; best-contract comparison and vertical helper | Evidence only; saved run declares no capital authority |

Latest saved-run EV-3 has zero evaluated rows despite complete stage execution. Fixing only the horizon validator cannot establish EV accuracy: state geometry support, quote availability, dividends, exit path and calibration must still reconcile.

### 6.10 Empirical option-EV shadow: additional existing owner

Owner: root `empirical_option_ev.py`, called after Q-OMEGA by `run_empirical_option_ev_shadow_stage`. This is separate from EV2, EV3 and the new C8 research lane.

- Percentile-return integration and forecast-vol scaling use actuarial quantiles to produce option-return scenarios; observation/support checks keep unusable inputs null.
- Path simulation samples innovations by interpolating quantiles, then recentres and rescales sampled innovations; prices evolve exponentially using vol and a `−.5 daily_variance` drift term.
- Intraday crossing is approximated with a Brownian-bridge crossing probability between closes; target/stop first passage determines exits; ambiguous ordering is conservative.
- Quote-calibrated IV and BS exit repricing, spread/friction, expiry buffer and p10/p50/p90 vol scenarios produce cautious/middle/upside path returns.
- Share-expression comparison uses Abdi–Ranaldo high/low/close spread estimate; negative estimated squared spread clipped to zero, insufficient support missing.
- Expression preference compares cautious option and share returns; both≤0→NEITHER, missing inputs→unavailable.

These are **model scenarios**, not observed option bids or a signal-conditioned C4 distribution. Sampling from terminal-return quantiles to daily innovations involves an extra modelling assumption. Read the complete settings and function expressions before claiming statistical validity. In the orchestrator this stage is noncritical shadow publication; its presence does not prove successful numeric coverage in every run.

### 6.11 DOI / deterministic scenario economics / ranking

Owners: `domain/deterministic_option_valuation.py`, `domain/contract_family_generation.py`, dynamic-options domain modules, canonical stores and production adapters.

| ID | Current method | Limits and downstream use |
|---|---|---|
| DOI01 | Family generation preserves ticker thesis, same-direction contracts, quote/lifecycle evidence | Existing multi-contract owner; not the same as old one-contract selector or new C6 |
| DOI02 | MON003 deterministic target/invalidation scenarios crossed with timing and IV×.8/1/1.2 | Conditional scenarios, no probability weighting |
| DOI03 | Entry=ask×(1+entry_bps/10000); exit=theoretical value×(1−exit_bps/10000); net return=(exit−entry)/entry | Model/friction adjusted, not necessarily observed future bid |
| DOI04 | `ranking_score_uncalibrated=median(favourable returns)+min(adverse returns)` | Explicit utility heuristic, **not EV** |
| DOI05 | Early-exercise/dividend/corporate-action guard labels OOD/materiality; missing entry leaves utility null | Model applicability must survive display and ranking |
| DOI06 | Chronological logistic model, then separate Platt calibration; holdout Brier/log-loss/ECE/baseline comparisons | Existing probability-learning code, not absent architecture; accepted-model status and inference support must be checked |
| DOI07 | Logistic p=sigmoid(beta·standardized features+intercept); calibrated p=sigmoid(a+b×raw logit) | Imputation/scaling must be fitted on training only |
| DOI08 | Brier=mean((p−y)²); log-loss clipped at1e−12; ECE=sum(bin_n/N×abs(bin_pred−bin_observed)) | Quality metrics need chronological support; no arbitrary 80% “confidence” claim |
| DOI09 | Calibrated rank utility=`w_d deterministic+w_l P(liquidity)+w_p P(positive)+w_t P(target_before_stop)−w_u uncertainty`; nonnegative weights sum1 | Only complete accepted components; otherwise deterministic fallback/no-comparable-score |
| DOI10 | Ranking policy acceptance compares held-out reward lift, coverage and temporal stability; contract-switch margin/hysteresis | Do not display deterministic fallback as calibrated priority |
| DOI11 | Lifecycle and immutable assessment identities, replay conflict detection | Reprocessing one session is not a new independent outcome; failed same-session replay must remain visible |

Current config says outcome capture enabled but model activation disabled pending acceptance. That is not proof that every DOI model has sufficient training data or is active. Latest receipt's ranked55 versus574 and lifecycle conflicts are diagnostic leads needing stored-family identity reconciliation.

### 6.12 New TEV C3–C8 working-tree additions

These additions implement parts of the agreed separation but do not supply both completed EVs.

| ID / owner | Current behaviour | Not supplied yet |
|---|---|---|
| TEV01 `structure_episode.py` | Dated observation reducer: persist/suspected/developing/failed/new range; no forced periodic phase change | Validated OHLC-derived episode detector and historical transition model |
| TEV02 `forecast_path_label.py` | Side-correct first passage on ordered complete OHLC; same-bar both→adverse and flag; gaps censor; matured survivor return | Integration as the single production label owner; duplicates C12 |
| TEV03 `competing_path_estimator.py` | Standalone competing-hazard/cumulative-incidence baseline with session-block bootstrap and support policies | Production-supported C4 path set, feature conditioning, calibration and all-population wiring |
| TEV04 `descriptive_forecast_handoff.py` | Convert governed Discovery CALL/PUT to BULL/BEAR, validate cut-off/session/stale/geometry, preserve population | Numeric underlying expectancy, interval and weighted direction/move/time path distribution |
| TEV05 C5 packet publisher | Immutable packet/receipt hashes; qualitative confirmation/delay/failure scenarios with null probabilities | Full dynamic second-order scenario composer; later GARCH not automatically merged back into frozen C5 |
| TEV06 `candidate_expression.py` / C6 adapter | Canonical hash/identity join; enumerate same-side, holdable contracts; deterministic expiry/ATM ordering, max20; overflow counted | Governed proof this cap/order preserves best economical candidate; duplicates family owner |
| TEV07 `option_path_valuation.py` | Pure qualified-path valuation interface with ask entry, friction, event exits and model marks | Supported C4/C7 paths in the live publisher |
| TEV08 C8 publisher | Calls `value_long_option_paths(None,None)` for governed disposition; `ev_usd`, `ev_fraction`, `numeric_ev`, `best_expression` remain null; numeric valuation count0 | Agreed exact-option EV and preferred expression |
| TEV09 research path baseline/vectorized pricer | Nonoverlapping same-ticker20-session current-known relative OHLC paths;≥12 paths; mean simulated ask-to-model-bid returns and bootstrap | Signal-conditioned physical distribution, PIT forecast proof, robust dependence handling and held-out calibration |
| TEV10 Morning revision publisher | Append immutable dated events tied to frozen C5 hash | Numerical probability/path updates and same-service C8 revaluation |

Research lane assumptions are explicitly rate0/dividend0/base commission0, constant base IV; adverse IV×.8, round-trip commission$2 and extra25% current spread each side. It uses session time/252 for its BS years, unlike calendar time in other pricers. Model exit mark less half current spread is a **bid proxy**, not a real bid. Bootstrap200 uses sorted sample means indices4/195. Nonoverlap does not establish independence across regimes.

The live governed C8 nulls are honest but incomplete. The separately displayed research numbers must not substitute for signed ticker EV or option EV. Duplicate label/pricer/generator/estimator owners must be reconciled by governance, not silently retired during this audit.

### 6.13 Market-physics and probability-score companions

Owners: `vanguard/physics_state_engine.py`, `probability_engine.py`, scenario builders/routers.

| ID | Current formula / rule | Interpretation |
|---|---|---|
| PH01 | Directional-force weighted momentum/control proxies; force alignment=majority sign fraction×100 | Reused price inputs are not independent corroboration |
| PH02 | Inertia=.55ADX+.25abs(force)+structure/phase bonuses; vol pressure=.45ATR-rank+.35IV-rank+.20compression energy | Clipped score, not physical units |
| PH03 | Entropy=.45(100−agreement)+.25(100−abs(force))+.20(100−inertia)+.10excess-vol pressure | Heuristic disagreement/chop index, not estimated information entropy |
| PH04 | Energy=.35compression+.25vol pressure+.20abs(force)+.10inertia+.10(100−entropy) | 0–100 summary score |
| PH05 | Transition “probability”=.25actuarial+.25energy+.20alignment+.15vol pressure+.15(100−entropy)−.10friction | Score transformation labelled probability; empirical calibration required |
| PH06 | Instability=.35entropy+.25pressure plus macro-drift/sector conflict bonuses | Macro can alter a diagnostic display score; verify it cannot indirectly gate/rank contrary to governance |
| PH07 | Hidden-state and transition labels by score thresholds; physics-forward verdict projection | Rule-based labels, not a learned hidden-state model |
| PR01 | Explicit breakout/rejection/drift accepted and normalized if positive and sum within.05 of1 | Rounded components may need tolerance reconciliation |
| PR02 | Otherwise breakout=clamp(.25+composite/200,.25,.65), rejection=clamp(.45−composite/250,.10,.45), drift=remainder clipped.05… .50; normalize | Heuristic prior, not fitted target/stop incidence |

“Reasoning” here means explicit evidence/state/rule relationships. No claim is made that naming scores physics/probability creates a trained neural, Bayesian or reinforcement-learning engine.

### 6.14 EIL, monetisation policy and decision/execution ceilings

Owners: root `execution_intelligence.py`, five strategy modules, `execution_intelligence_runner.py`, `avshunter_monetisation_policy.py`, `execution_decision_engine.py`, `execution_gate.py`, execution schema and domain guards.

| ID | Current calculation / rule | Downstream effect |
|---|---|---|
| EX01 | EIL composite `.50 liquidity+.40 IV+.05 GEX+.03 order-book+.02 POC` | Liquidity/IV dominate; same evidence may also appear in other scores |
| EX02 | EIL enrichment modifiers +10 preferred /−15 conflicting branches; underlying sub-strategies produce warnings/block/defer | Must distinguish evidence availability from scored proxies |
| EX03 | EIL EV_net=EV2_raw−measured live spread cost; EV_score=clamp(50+200EV2_raw,0,100); EV_confidence=composite/100 | Not a fresh independent exact-contract expectation; source/unit compatibility matters |
| EX04 | Policy rules FATAL/REVIEW/TAX and size multipliers; contradiction tax min(.03×count,.15), priority−2/count | Recommendations/priority, not account allocation; macro authority retirement must be verified at final owner |
| EX05 | EDE hard spread/delta/live-BE checks; EOD skips missing inputs with explicit SKIP; EIL advisory in EOD | SKIP is not PASS/measured; final Morning checks still required |
| EX06 | EDE actuarial confidence policy: absent0, sample<20→.30,20–49→.60,≥50→1 | Policy support weight, not statistical confidence interval |
| EX07 | EDE rank =final score (else composite)×verdict multiplier GO1, ARMED.9, ARMED_HALF.7; blocked/wait→−1 | Different from DOI, EOD slate and Lab sorting |
| EX08 | Shared quote spread `(ask−bid)/mid`; actual quote age; delayed feed effective age=max(age−disclosed delay,0) | Effective freshness is not real-time entitlement or thesis validity |
| EX09 | OLM terminal invalidation/realized move block; contract-reprice→repair; pending/requote→review; positive continuation needs ACTIVE thesis+exact EXECUTABLE_NOW+supported lifecycle | CONTINUE only permits final gate evaluation; never grants capital |
| EX10 | Final gate side-checks sourced invalidation, exact contract, current monetisability/liquidity/Morning ceilings and advisory authority violations | BUY_NOW/BUY_SMALL remain human-approval workflow labels; no order placement |

Execution viability intentionally says EV/RR cannot override missing hard execution evidence. But a quote-unavailable contract should not be confused with an invalidated underlying thesis. Audit both state axes through each consumer.

### 6.15 EOD candidates, exits and horizon routing

Owners: `eod_candidate_engine.py`, `macro_horizon_router.py`, exit-plan domain/helpers and Morning candidates.

| ID | Current method | Meaning / consequence |
|---|---|---|
| EO01 | Candidate failure class and lane separate structural thesis failure, contract repair, review and genuine fatal block | Preserve opportunity population and reason; count all partitions |
| EO02 | Structural-conviction score from ticker evidence, candidate tier A/B/C, shadow opportunity score and repair score | Multiple score vocabularies; do not treat every score as one common probability |
| EO03 | Monetisation fit adds OIS/RR/trigger/catalyst/contract/direction components, optional bonuses/taxes; labels≥72 execute-like,≥55 review else watch | Heuristic fit label, not final capital permission |
| EO04 | Exit wall/scaling/runner plan uses direction and cumulative volatility budgets plus sourced geometry | Distinguish structural invalidation from synthetic plan reevaluation trigger |
| EO05 | EOD slate ranking plus trigger-neutral rank audit measures trigger impact | Ranking effects need full producer→consumer tests, not just formula tests |
| EO06 | Current horizon router direction-agnostic; thesis holding context preferred, DTE fallback; unknown/expired instrument blocked | Macro parsed for advisory context, old macro permission helpers remain present but not automatically active |
| EO07 | Move window, holding ceiling, expiry buffer and event-first exit separately published | EV3 exact-endpoint restriction currently conflicts with this separation |

### 6.16 Morning: evidence updates, quotes and execution

Owners: `morning_gate.py` orchestrated path, `morning_validation.py` compatibility/CLI calculations, `morning_handoff_finalizer.py`, lifecycle/quote observations and revision packets. Presence of both Morning modules requires call-path verification.

| ID | Current formula / rule | Interpretation |
|---|---|---|
| AM01 | Side-aware target/stop/trigger checks on today's underlying evidence; exact-contract requote and freshness | Price confirmation and current option liquidity are different facts |
| AM02 | Frozen EOD joined to later observations by run/ticker/contract; Morning ledger appends revisions | Do not rewrite the Evening claim using knowledge obtained later |
| AM03 | Compatibility Morning score: abs drift bands (25/15/5), direction-relative VWAP (20/10/0), spread (20/12/5), IV (15/12/7/3), RVOL (10/6/3), tier carry (10/7/4) | Scored suitability/timing, not calibrated profit probability; hard rejects override score |
| AM04 | Compatibility RVOL extrapolation=`today_volume×20/previous_volume` | Fixed elapsed-time assumption; validate at actual intraday time before trusting |
| AM05 | Exit runner now requires ten-session budget; missing budget→review, not five-session fallback | H1 repair behaviour visible in source; do not infer all horizon consumers fixed |
| AM06 | Generated plan invalidation may use spot±.35×max(5d move/wall/2% proxy) if absent | Explicitly labelled reevaluation trigger, **not sourced stop loss**; must never fill missing governed invalidation |
| AM07 | Final Morning→Lab/Interpreter handoff manifests, identity reconciliation and terminal completion | A candidates CSV alone is not Morning completion |

No Morning run was launched for this assessment. Latest saved run remains pre-Morning; current Morning numerical TEV update/revaluation is incomplete.

### 6.17 Intelligence Lab: source selection, presentation and sorting

Owners: `contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py`, `intelligence-lab/static/index.html`.

| ID | Current projection/rule | Human-facing consequence |
|---|---|---|
| LAB01 | Mode-aware EOD/Morning source selection; manifest plus stage CSV/ledger joins; cache keyed by source signatures | Morning data must supersede corresponding current fields while preserving frozen EOD values |
| LAB02 | Resolve contradictory legacy verdicts with final execution ceiling, lifecycle, quote/economics and Morning status | Green GO text is not sufficient if current contract/stop evidence fails |
| LAB03 | Default ordering GO, GO_LIMIT, PROBE, review, repair, Morning-required, armed, wait, blocked; within status descending priority then ticker | Not the agreed ticker-EV-first / expression-EV-second ranking |
| LAB04 | Convexity only accepted with explicit qualified source and scale; 8-condition count preserved; verdict-encoded/unqualified values withheld | Missing/unsupported convexity must not be replaced with a numeric zero or matching value assumption |
| LAB05 | Geometry completeness canonical volatility preferred, missing stops/targets and degeneracy rules counted | Run health is coverage diagnostic, not forecast accuracy |
| LAB06 | Final manifest separates technical health, semantic defects, prep and execution permission | latest run92/DEGRADED does not mean92% chance of profit |
| LAB07 | API/HTML display of forecast and expression/research fields, missing values and badges | Reader must see source/method/unit/as-of; frontend has not been screenshot-tested in this assessment |
| LAB08 | C5 loader/publisher called from Lab owner | Read-model side effect currently exists; new plan proposes moving publication out; not fixed merely by documentation |

A Lab verdict is a projection, not a new quantitative engine. Nevertheless sorting, aliases and blank handling can change what a human notices. These are first-class verification targets, not cosmetic matters.

### 6.18 Interpreter, interactive desk and WAR

Owners: `pipeline_interpreter/interactive_desk.py`, snapshots/evidence/confluence readers, provider adapters, `automation_v2/lab_structured.py`, WAR assembler and domain provenance modules.

| ID | Current logic / computation | Output / authority |
|---|---|---|
| INT01 | One–five distinct selected tickers bound to run; evidence digest max20k chars, deeper max40k; overflow fails explicitly | Bounded narrative input, not screenshot-dependent forecasting |
| INT02 | Frozen snapshot, current accepted Morning/later evidence, exact identity and cut-off validation | Claims must cite eligible source evidence; latest does not mean future-to-cut-off is permitted |
| INT03 | Confluence chain: sector evidence→ticker relative evidence→governed trigger→dated catalyst→exact-contract economics, with counter-case | Missing link remains missing; report cannot repair Lab data |
| INT04 | Provider report/answer schema checks, citations and hidden-order limitations; persist attempts and results; no automatic retry of UNKNOWN outcome | Run-bound JSON reports and questions; narrative is advisory |
| INT05 | Configured cost bound=`[(input_chars+25,000)×input_price+8,000×output_price]/1e6+2×search_call_price` | Conservative configuration estimate, not vendor billing/pricing validation |
| WAR01 | Freeze Evening claims, append later layers, reject future evidence; timeline sort and provenance | JSON authoritative report record; HTML rendered without provider calls |
| WAR02 | Event→sector→ticker→contract links MEASURED/INFERRED/MISSING; complete chain only if weakest MEASURED | Link-status assessment, not causal proof of cash transmission |
| WAR03 | Corroboration groups signals sharing any upstream source (transitively); vote count=number of groups | Multiple fields from one model/provider are not multiple independent confirmations; empty lineage needs conservative review |
| WAR04 | Calendar empty-valid versus unavailable/read-failed; per-ticker coverage and exact quote freshness/executable assessment | No-data answer must be informative, not disguised as neutral |
| WAR05 | Pure escaped HTML renderer from saved JSON; quote observation persisted separately | Reopening report must not initiate spend, mutate history or change execution authority |

The Interpreter can explain a measured/inferred trap or crowd-at-wall hypothesis, but daily bars/OI cannot reveal hidden orders with certainty. It is an explanation/challenge layer, not an independent issuer of ticker direction or trade permission.

### 6.19 C12 / historical outcomes / trade journal

Existing owners: `avshunter/c12_outcome/{model,geometry,passage,estimators,base_rate,expression,signals,service}.py` plus stores, session clock and DOI outcome-learning.

| ID | Current computation / rule | Why it matters |
|---|---|---|
| OUT01 | Geometry classifies side, reference, invalidation and target; missing/wrong-side geometry→not scorable | Cannot learn target-first probability from malformed examples |
| OUT02 | Chronological first-passage TARGET_FIRST/STOP_FIRST/AMBIGUOUS/TIMEOUT/OPEN_CENSORED/DATA_GAP | Ambiguous daily double touch is adverse in estimator; open/gap not treated as ordinary loss |
| OUT03 | ATR-matched no-skill universe: barrier distances abs(level−reference)/ATR; place equivalent signed barriers on each universe ticker | Broader base sample than own pipeline runs; feature conditioning is separate |
| OUT04 | Aalen–Johansen hazards `hT=dT/N`, `hS=dS/N`; `S_t=S_prev(1−hT−hS)`; `F_T+=S_prev hT`, stop analogous | Target incidence+stop incidence+survival=1 for scored curve; not binary completed-case win rate |
| OUT05 | Session-block bootstrap, paired observed/base bootstrap and excess-incidence intervals | Independent unit is evidence/session block, not every row; check dependence/block design |
| OUT06 | Exact option entry recorded ask else same evidence-session chain ask; exit same contract's planned-date EOD bid; missing→MARK_UNAVAILABLE | No nearest-date or different-contract substitution |
| OUT07 | Gross quoted P&L=(exit_bid−entry_ask)×multiplier; return=bid/ask−1 | This C12 mark helper does **not subtract commissions**; separate signal/expression policy can apply costs |
| OUT08 | Resolution/session-window expiry-buffer exit, only publish once date≤as-of | Full observation paths, maturity and censor reasons required |
| OUT09 | Signal plans, delayed quote handling, caps, model marks, max drawdown, counterfactual cohort and prospective issue ledger | Hypothetical/revalued versus recorded quotes and manual fills must stay separate |

Existing censor-aware and base-rate owners mean “survival analysis is absent” would be incorrect. What remains is verified, version-equivalent wiring and any accepted predictive challenger. A correct historical mark is not proof that the trader could capture that price intraday.

## 7. Cross-stage relationship contracts

| Producer→consumer | Must stay invariant | Failure that verification should catch |
|---|---|---|
| Price store→Discovery→Vanguard | Evidence session, adjustment/security identity, feature version | Today-corrected history assumed available at past decision |
| Wyckoff/Crabel→fusion→CSV→C5 | Typed mode/phase/compression and input provenance | Typed state exists in function but consumer reads blank legacy column |
| Discovery→Vanguard | Underlying direction and evidence preserved; independently measured opposition allowed | Options unavailable converted to no underlying edge |
| Vanguard→C5→C6/C8 | Frozen thesis identity; option-neutral forecast; same direction/path set | Option premiums in ticker EV or attractive option reversing ticker direction |
| Vol forecast→EOD/trigger/Morning/Lab | One cumulative session budget and validation convention | Increment used as full horizon; calendar/session mix; missing10d replaced with5d |
| Canonical chain→contract candidates→selected quote | OCC/right/strike/expiry/multiplier/dataset/run | Same ticker but different contract quote joined as executable |
| EOD→Morning | Frozen original plus append-only observations | Current quote age invalidates original thesis without price evidence |
| Execution ceiling→Lab→Interpreter/WAR | Same permission ceiling and missing-data states | Fluent text or green badge grants authority refused upstream |
| Decisions→C12/DOI/journal | All presented/rejected/missed candidates, exact path and fill/quote basis | Backtest selection bias; unresolved rows called losses; missed winners excluded |

## 8. Independent reference checks to build next

These are proposed verification cases, **not tests executed today**. Use a different reference implementation or hand worksheet; never have the production formula certify itself.

| Check | Known reference / required invariant |
|---|---|
| Trading-session vol | Annual vol.30, five sessions→`.30 sqrt(5/252)=.0422577` (4.22577%); ten→.0597614; twenty→.0845154 |
| Legacy calendar clock | Five calendar days gives 3.5714 assumed trading days and ~3.57143% at vol.30; not equal to five sessions |
| Spread | bid2.00 ask2.20: mid2.10; fraction.0952381; percent9.52381; entry at ask and exit same bid loses9.09091% before fees |
| Quoted contract P&L | ask2.20 bid2.00 multiplier100→−$20, not−$0.20; commission lowers it further |
| Underlying geometry | BULL100/target110/stop95 mirrored BEAR100/target90/stop105 must preserve signed target/stop logic |
| Cumulative incidence | Two initial cases: target at session1 and stop at session2→F_target=.5, F_stop=.5, survival0; censoring must not manufacture a loss |
| Legacy intrinsic proxy | CALL K100 mark2 target110→intrinsic10, net-return proxy4.0; payoff multiple5.0; neither proves target probability or today's exit bid |
| Probability-weighted option outcomes | p(.4,.3,.3), returns(1,−.5,−.1)→EV.22; adverse IV/costs recomputed separately |
| EC08 flattening | Positive edge gaps1 and10 both yield half-premium win payoff; verify whether downstream labels incorrectly imply move-sensitive EV |
| Greek scaling | IV30%→31% versus30%→40%; test provider vega convention; negative theta must not eliminate modeled decay cost |
| Black–Scholes limits | Expiry intrinsic, zero-vol limit, put/call parity with owner dividends, Greek finite differences, American materiality |
| Source missing | Blank gamma/IV/stop never becomes measured0, neutral50 or synthetic valid stop |
| Producer→consumer | Real Discovery/Vanguard row reaches EV and returns evaluation or correct typed rejection; completion with0 valuations fails functional acceptance |
| UI parity | EOD/Morning JSON→LabAPI→HTML→Interpreter same identity/value/unit/state/source; fresh quote not joined to old contract |

For predictive testing: register variants, freeze temporal cohorts, purge/embargo overlapping outcomes, separately fit/calibrate/test, report usable coverage and tails as well as mean returns, and retain unanswered/censored cases. An 80% logic-confidence target cannot be asserted by setting score80 or training on selected winners.

## 9. Verification findings and impact of leaving them unresolved

These are assessment findings/risks, not newly assigned release grades or implemented fixes.

| Priority | Finding | Impact if unchanged | Required evidence |
|---|---|---|---|
| 1 | C5 lacks supported ticker expectancy; live governed C8 publishes null EV/best expression | Agreed two-EV solution remains incomplete; research number can anchor trader incorrectly | Supported same-path underlying and option products, producer→consumer coverage |
| 1 | EV3 exact hold/bucket coupling plus latest zero evaluations | Running EV stage produces no numerical decision intelligence | Real population rejection/evaluation reconciliation, clocks repaired in correct owner |
| 1 | Untracked critical imports/partial publishers | Clean checkout may fail; advisory exceptions can abort main run | Import closure and end-to-end exception/immutability tests on governed release snapshot |
| 1 | Legacy options viability inside ticker gate / multiple direction owners | Wrong option/no quote may suppress valid ticker; direction conflicts persist | Ticker decision invariant under option unavailability/price changes |
| 1 | Canonical session budget versus legacy calendar increments | Targets/runner/economics/rank disagree about available move | Independent units and full handoff parity for every horizon |
| 2 | Duplicate EV2 files/pricers/generators/labels and dynamic basename imports | Drift, false test coverage and incorrect attribution of active formula | Resolve actual imported owners; explicit consolidation/change approval |
| 2 | HAR fit slice starts at index23 with180 cap, while latest features use end of input | Potential early-window calibration applied to latest market state; actual effect depends on length/order of supplied history | Dated reference reconstruction, intended rolling-window specification and sensitivity comparison |
| 2 | Macro text/list-count transforms, zero-via-`or` fallbacks and future-age freshness | Heuristic context can be read as calibrated/measured evidence; valid zero or future time can be misclassified | Raw series/units/source trace, independent boundary tests and final authority checks |
| 2 | Heuristic numbers called probability/EV/confidence | Trader reads a fitted probability where only score transform exists | Naming/source/method flags, calibration acceptance and authority trace |
| 2 | EC08 positive-gap payoff flattened; EC02 expiry proxy used beside path economics | Economics may not discriminate useful move sizes or holding-time opportunity | Formula-spec review and downstream sensitivity/ownership tests |
| 2 | Compression/modephase publication versus matching mismatch | Valid observations lost/misclassified, history matches unlike states | Feature-version and CSV→C5→historical equivalence |
| 2 | Missing selected stops, profile coverage and stale/conflicting macro row context | Attractive UI outputs can carry incomplete or stale decision evidence | All-population reason/source reconciliation; preserve thesis versus expression state |
| 2 | Macro display-only governance versus proposed forecast conditioning and diagnostic scores | Unapproved authority drift or missed intended context | Versioned business decision and evidence-path effect tests |
| 2 | EIL spread/EV units, Greek/day/vol-point conventions,100 hardcoding | Wrong economic costs and adjusted-contract dollars | Signed unit contract, exact multiplier and reference calculations |
| 3 | Shared log contains test errors under other IDs; old labels/package terminology | False monitoring alarms and incorrect root-cause attribution | Run-scoped terminal evidence and traceable diagnostic events |

The new build plan contains suggested remedies and scope cuts. Those are not automatically accepted amendments to the signed design. This document records current behaviour rather than choosing a replacement without permission.

## 10. Governance and use by an independent verifier

For each business calculation ID, the verifier should create one result row:

```text
ID; active resolved owner; source SHA; config version/hash;
inputs/source identities/as-of; units; actual formula; agreed formula;
independent reference result; production result; difference/tolerance;
missing/boundary behaviour; producer-consumer result;
mathematical verdict; specification verdict; predictive verdict;
affected outputs/consumers; defect grade; workaround; evidence links
```

ACK approves business scope/formulas and shipment; the builder implements in the named owner; an independent verifier challenges calculations and end-to-end behaviour. The verifier must not fix production, grant capital or mark its own build correct without authority. An unresolved formula cannot be passed merely because a legacy test expects the same wrong answer.

Definition of shipped from this chat: completed build and implementation, followed by testing and an **ACK-started** Evening/live proving with no grade0/1/2 defects; grade3 requires documented workaround. This document satisfies an **inventory/assessment task**, not that release condition.

## 11. Source register and navigation

All paths below are in the assessed repository. For any owner not linked here, search the function/source JSONL by its repository-relative `file`; use `line` and `end_line` to inspect original source. Register IDs uniquely identify syntax records, not market observations.

### Current entry points and displays

- [Evening/Morning orchestrator](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/intelligent_orchestrator.py)
- [Scanner](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/avshunter_universe_scanner.py)
- [Discovery](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/avshunter_discovery_ULTIMATE.py)
- [Wyckoff engine](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/WyckoffEngine_3101_v2.py)
- [Fusion rules](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/swing_fusion.py)
- [Manifest/reference Vanguard adapter](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/run_vanguard_from_packages.py)
- [Options Intelligence](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/avshunter_options_intelligence.py)
- [EIL runner](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/execution_intelligence_runner.py)
- [EIL strategies/composite](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/execution_intelligence.py)
- [Decision engine](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/execution_decision_engine.py)
- [Execution gate](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/execution_gate.py)
- [EOD candidates](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/eod_candidate_engine.py)
- [Morning gate](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/morning_gate.py)
- [Morning score/exit helper](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/morning_validation.py)
- [Lab authoritative projection](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/contracts/lab_control.py)
- [Lab API/cache](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/intelligence-lab/intelligence_lab.py)
- [Lab frontend](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/intelligence-lab/static/index.html)
- [Interactive desk](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/pipeline_interpreter/interactive_desk.py)
- [WAR renderer/provenance](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/war_report_provenance.py)

### Main numerical owners

- [Macro score normalization](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/normalise_macro_contract.py)
- [Macro packet formulas and freshness](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/macro_quant_packet.py)
- [Regime prior lookup](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/contracts/macro_regime_safety.py)
- [USMI scenario and sector rules](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/macro_domain/us_money_index.py)
- [USMI row projection](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/macro_advisory_context.py)
- [Legacy sector alignment](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/scripts/sector_alignment.py)
- [Vol forecast](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/layer3_forward_variance.py)
- [Canonical volatility budget](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/volatility_budget.py)
- [Layer4 mispricing](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/layer4_mispricing.py)
- [Actuarial state query](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/vanguard/layer2_statistical/actuarial_query.py)
- [Legacy ticker edge detector](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/vanguard/layer2_statistical/edge_detector.py)
- [Root EV2](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/ev_engine_v2.py)
- [Vanguard EV2](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/vanguard/ev_engine_v2.py)
- [EV3 validator](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/vanguard/ev3_stage0.py)
- [EV3 valuation](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/vanguard/ev_engine_v3.py)
- [Empirical shadow EV](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/empirical_option_ev.py)
- [Deterministic contract scenario valuation](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/deterministic_option_valuation.py)
- [DOI probability fitting/calibration](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/canonical_data/dynamic_options_probability.py)
- [DOI ranking](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/dynamic_options_ranking.py)
- [C12 cumulative incidence](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/avshunter/c12_outcome/estimators.py)
- [C12 matched universe base rate](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/avshunter/c12_outcome/base_rate.py)
- [C12 exact quoted outcomes](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/avshunter/c12_outcome/expression.py)
- [Current C5 descriptive composer](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/domain/descriptive_forecast_handoff.py)
- [Current C6 publisher](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/contracts/expression_candidate_packet.py)
- [Current C8 disposition/research publisher](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/contracts/expression_valuation_packet.py)
- [Governed numerical constants](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/config/governed_constants_v1.json)

### Release evidence and annexes

- [Weekend manifest/ledger build receipt](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS-PKG-002_P1_P4_BUILD_RECEIPT_20260927.md)
- [Latest TEV build plan and independent review](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/decision_map/AVS_TEV001_BUILD_PLAN_20260927.md)
- [Latest inspected final run manifest](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/output/runs/20260927_205123/final_run_manifest.json)
- [Latest inspected EV3 stage receipt](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/data/output/runs/20260927_205123/ev3_shadow/ev3_shadow_phase_status_20260927_205123.json)
- [Inventory summary](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/inventory_summary.json)
- [Source/hash manifest](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/source_manifest.jsonl)
- [Function register](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/function_register.jsonl)
- [Calculation/condition register](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/calculation_condition_register.jsonl)
- [Import/call register](C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/dependency_call_register.jsonl)

## 12. Assessment conclusion

AVSHUNTER has substantial working evidence, pricing, lifecycle and outcome functionality. The weekend manifest/ledger work materially changes its storage/call boundary and has saved-run completion evidence. But a completed workflow is not equivalent to completion of the agreed ticker-forecast→option-valuation numerical design.

The next verifier must concentrate on **actual owner resolution, unit/clock consistency, underlying-versus-expression separation, numeric coverage, missing-data honesty and end-to-end consumer parity**. The main risk is not a lack of formulas: it is multiple formulas with overlapping names, different assumptions and incomplete handoffs being read as one coherent result.

This assessment changes no production source, database, universe, broker configuration or run. It creates only documentation and machine-readable source inventories.
