# AVS-REV-002 — AVSHUNTER Pipeline Functional Reference: Discovery, Wyckoff/Crabel, Vanguard, Options Intelligence, EIL

**Date:** 2026-09-01
**Scope:** the 18 Python files reviewed in full (Discovery, orchestrator, Wyckoff engine, Wyckoff/Crabel precor, Options Intelligence, EIL engine + runner, Vanguard Layer 1 auction (5 files), Vanguard Layer 2 statistical (4 files), EV3 engine + stage 0)
**Method:** four parallel Claude static-analysis reviews, every function read; all claims carry file:line evidence. Findings are static-analysis results — the top items should be confirmed against a run artefact before being treated as CLOSED-standard facts.
**Purpose:** the baseline "what the code actually does" reference for the from-scratch review of why signals contradict each other and the edge is lost by the end of the run.

---

## PART I — Executive synthesis

### I.1 The one-sentence answer to "why do signals contradict by the end"

The pipeline has **at least nine independent places that originate a directional opinion** and **six sequential rewriters of the final verdict**, connected by ticker-keyed joins and first-present column chains rather than one governed record — so by Phase 10 a single row routinely carries five direction-flavoured fields written by different engines under different rules, and the verdict the Morning Gate reads is the last writer, not the best evidence.

### I.2 The directional signal chain (who writes direction, in run order)

| # | Stage | Field(s) written | Rule | Ambiguity behaviour |
|---|---|---|---|---|
| 1 | WyckoffEngine_3101_v2 | `trade_direction` (LONG/SHORT/NONE) | event∈long/short list AND control∈{side, EQUILIBRIUM} (L869–878) | silent NONE, no reason |
| 2 | WyckoffEngine_3101_v2 | `execution_bias` (BULLISH/BEARISH/OBSERVE_ONLY) | control alone (L915–923) — **different rule than #1, same file** | OBSERVE_ONLY |
| 3 | wyckoff_crabel_precor v2 | `wyckoff_mode`, `intent`/`precor_intent_raw` | phase×mode×control table (L658–732); mode fallback = sign of 60-bar drift @conf 70 (L646–651) | never UNRESOLVED; 3 rules resolve ambiguity toward BUY_SETUP (L692, 727–728, 732) |
| 4 | swing_fusion (not in upload) | `fusion_direction` | external | missing → 'NONE' silently (discovery L1375) |
| 5 | Discovery `_reconcile_intent` | rewrites `precor_intent` | incl. Rule 3: SELL_SETUP→BUY_SETUP in mature uptrends (L331–333) **without re-syncing fusion_direction** | helpers default neutral on exception, silently disabling rules |
| 6 | Discovery Stage-0 governance | `discovery_direction_preliminary`, `direction`, authority=DISCOVERY_PRELIMINARY_ONLY | `preliminary_discovery_direction(fusion, wyckoff)` (L1576–1583) — "never default to CALL" | explicit UNRESOLVED ✓ |
| 7 | Vanguard edge_detector | `edge_direction` (CALL/PUT) | control ±40 + migration ±30 + prob_up ±20 + trend ±10 (L503–534) | **tie/ambiguity → `return "CALL"` (L534)** |
| 8 | Options Intelligence | `ctx['direction']` → `options_direction` | external `resolve_governed_direction` (contracts/direction_governance.py — the governed authority per DIR-001) | governed UNRESOLVED/STRANGLE → chain suppressed ✓; but `parse_structural_context` L3947–3960 *fabricates* a Vanguard edge direction from raw probabilities as arbitration input |
| 9 | Orchestrator Phase 1B horizon router | `_instrument` | first-present of instrument/options_direction/strategy_type/direction, **default "CALL"** (L1445–1452) | **NONE → CALL; literal "UNRESOLVED" passed as an instrument** |
| 10 | EIL context builder | `signal_direction` | `row.get('direction')` **default "LONG"** (execution_intelligence.py L683) | silent LONG |
| 11 | EIL runner audit contract | `direction_conflict_status` | rewrites every non-BLOCKED row to MITIGATED/NO_CONFLICT (L2675–2678) | **erases UNRESOLVED after the candidate gate used it** |

Layers that *should* be direction-neutral but carry a structural tilt: Discovery priors penalise DISTRIBUTION −12…−15 in every regime (L666–676); Vanguard `structure_quality` encodes above-VWAP as STRONG (state_calculator L521–634); every actuarial outcome column is long-framed (`outcome_hit_10pct_up` etc.) so PUT verdicts are certified by long-side EV (edge_detector L288–292); auction scenarios and scenario_builder targets are long-only geometry even for PUT (auction_synthesizer L251–307, scenario_builder L186/310/425).

### I.3 Where the edge is lost — the five highest-confidence mechanisms

1. **Value-migration sign inversion (Vanguard L1).** `auction_synthesizer` builds session profiles oldest-first (L61–67); `value_migration` requires newest-first (docstring L34) and computes `poc[0] − poc[-1]` (L84). Direction and consistency are **inverted**: a rising value area scores −30 toward PUT in `edge_detector._determine_direction` (L510–513). This is a live sign error in the second-largest directional weight in the system. *Confidence: high — arithmetic verified in both files; confirm with one fixture run.*
2. **NONE→CALL laundering at Phase 1B** (orchestrator L1445–1452) directly violating Discovery's own governance rule (discovery L1576–1583), plus EIL's silent LONG default (execution_intelligence L683). The DIR-001 Discovery fix removed the `else: 'CALL'` — these two downstream defaults reintroduce the same skew.
3. **Evening verdicts are scored on fabricated microstructure, then overwrite the pipeline's verdict.** Every evening run is EOD_SYNTHETIC (runner L332–343); S1+S2 = 90% of EIL composite weight run on synthesised spreads/L2 books/IV dispersion (runner L462–624), the synthetic book is skewed *by the trend input* so OBI "confirms" the input (L558–574), and at write-back `sb_final_verdict` is overwritten with the EIL passthrough `fd_verdict` (L3550–3553) with `EXECUTE_DEFER→WATCHLIST` (L368). The conviction built in phases 3–8 is replaced by a score on invented quotes.
4. **EV scale instability across the evening/morning boundary.** `_adjust_for_intraday_context` (actuarial_query L1233–1369) unconditionally re-defines EV on the target-hit basis whenever any intraday rows exist — its own docstring says ~50× inflation — while Gate 5 floors (0.0005–0.0020) were calibrated on the base scale. Evening TRADE / morning NO_EDGE flips follow directly. Run-time-dependent state (wall-clock volume scaling, state_calculator L590–616) compounds it.
5. **Gate erosion in Options Intelligence.** Score-based STAND_DOWN removed (any score → ARMED, L6042–6046), RR floor 1.0 not 1.5 (L6005), theta and wrong-strike gates demoted to warnings, `mark_synthetic` defaulting to the *lenient* EOD tier (L6011), dead event gate (L5885–5891), dead delta-weighted flow module (NameError swallowed every ticker, L6704–6707). The verdict column no longer discriminates — which reads downstream as "edge lost".

### I.4 Structural findings that make the contradiction *architectural*, not incidental

- **Two Wyckoff engines run on the same bars** with different control thresholds, phase rules and confidence regimes (honest 0–100 vs floored 60–82); both feed discovery. The "audit only" precor still emits `intent`, and its floored confidences systematically outrank the honest engine wherever confidences are compared.
- **Four incompatible state identities** in Vanguard/EV3 (9-dim `state_hash` written but never used; 10-dim actuarial match key; 6-dim `state_v2`; 7-dim EV3 key) and `behaviour_state_hash` required by the EIL handoff but computed nowhere in these files. UNKNOWN dims are silently dropped from the "EXACT" match (actuarial_query L500–526), widening cohorts while still labelling similarity 1.0.
- **Ticker-keyed joins with keep-first** everywhere in the orchestrator (L1521, L2792, L3241, L5134): any ticker carrying both CALL and PUT rows has one direction's fields silently applied to the other.
- **Six sequential rewriters of `eil_enriched`** and six writers of `pse_execution_mode`/`fd_verdict` per row; the handoff conflict guard then flips execution-like verdicts to WATCHLIST at the end (L5928–5935). The final CSV is the residue of a write war, not a resolution.
- **Insufficient data flows through as positive** at multiple points: acceptance INSUFFICIENT_DATA passes Gate 1 as favourable (auction_synthesizer L346–351); UNKNOWN sub-metrics earn partial credit (value_acceptance L405–428); empty profile reads as ABOVE_VALUE; missing macro → full-size GO_SELECTIVE (orchestrator L234–276); precor's insufficient-data output is labelled ACCUMULATION; the Wyckoff engine's error path fabricates `transition_bias="B"`.
- **Reporting contradicts computation** in several places (trading costs printed but not subtracted; macro bonus note claims "+3.0 OIS applied" while forced to 0; EVEngineV2 invoked and discarded) — so human review of run artefacts is actively misled.

### I.5 What this means for the logic/flow test plan (next step)

The layer-by-layer tests you asked for should be built against Part II below, but the five mechanisms in I.3 deserve targeted fixture tests *first* — each is cheap to prove or disprove with one synthetic input: (1) a rising-POC three-session fixture through synthesize→migration→edge_detector; (2) a direction-less row through Phase 1B and EIL ctx; (3) one evening row's EIL composite recomputed with spread source labels; (4) the same state queried with and without intraday rows; (5) a zero-score contract through derive_verdict. I can draft that test prompt on request.

---

## PART II — Per-file functional detail

The four full review briefs follow verbatim, with every function, formula, threshold and line reference.


---

# SECTION A — Discovery (`avshunter_discovery_ULTIMATE.py`) and Orchestrator (`intelligent_orchestrator.py`)

# FILE — `avshunter_discovery_ULTIMATE.py` (2,686 lines)

## A1.1 Role & invocation

Phase 3 Discovery scanner. Scans the whole universe, produces tiered candidates that seed everything downstream (packages → Vanguard → OI → EIL → EOD manifest). Invoked by the orchestrator as a subprocess (`run_discovery()`, orchestrator L1655-1661) with `--universe <csv> --progress-every 100 --force-update` plus `--scanner-context <json>` when the scanner ran.

CLI (`main()`, L2336-2349): `--universe` (default `config/tickers.csv`), `--data_dir` (default `data/daily`), `--output_dir` (default `data/output`), `--log_level`, `--force-update`, `--lookback-days` (90), `--progress-every` (100), `--scanner-context`.

Entry: `main()` → per ticker `load_bars()` → `scan_ticker_ultimate()` → `assign_discovery_horizon()`.

## A1.2 Inputs

- Universe CSV (`ticker` column required; sector/sector_etf/industry/macro_abstain optionally read, L1248-1270).
- Per-ticker OHLCV: canonical DB via `canonical_data.history_bridge` (CDS-2), then `data/daily/{ticker}.csv` cache, then Polygon API (`polygon_data_fetcher.PolygonDataFetcher`). Env: `POLYGON_API_KEY` or `MARKETDATA_API_KEY` (L2447-2451), `AVSHUNTER_RUN_ID` (L1013, L1053).
- Macro regime: `dropbox/macro/macro_intelligence_latest.json` via `regime_threshold_injector.apply_regime_to_config` (L2358-2361); sector signals from `extras.sectors` (handles the double-nested `extras.extras` wrap, L2372-2381).
- Scanner context: `scanner_context_{run_id}.json` → `cfg.vms_context` keyed by ticker (L2400-2422).
- `dropbox/macro/sec_activist_signals.json` (advisory only; ignored unless `advisory_only: true`, L2278-2294).
- `data/sector_map.csv` (L1229).
- Engines: `WyckoffEngine_3101_v2`, `wyckoff_crabel_precor_logic_v2.process_precore_signal`, `wyckoff_phase_validator`, `contracts.direction_governance.preliminary_discovery_direction`, and optionally `swing_fusion` + `asymmetry_gate_swing` (L42-74).

## A1.3 Outputs (all to `--output_dir`; timestamp = canonical run_id)

- `discovery_candidates_ultimate_{ts}.csv` — all signals, sorted by `['tier','lift_proxy_score']` (L2594-2596). Key fields (signal dict L1941-2201): `tier/tier_label`, `stock_price/entry_price`, `stop_loss`, `structural_stop(+_source)`, `structural_target(+_source)`, `phase`, `wyckoff_score`, `crabel_score`, `composite_score` (raw), `composite_adjusted`, `prior_adjustment/prior_label`, `lift_proxy_score`, Sprint-A repricing fields (`gap_pct`, `range_pct`, `range_expansion_vs_20d`, `dollar_volume_zscore`, `vwap_acceptance_score`, `abnormal_repricing_score`, `repricing_state`, `repricing_reason_codes`, `repricing_direction`), `candidate_lane`, Vanguard bucket fields, staleness fields, `win_probability`, `wyckoff_phase_bucket`+`wyckoff_phase_granular`, `adx_14`, `atr_percentile_rank`, `catalyst_proximity`, full Wyckoff evidence fields, direction fields (`discovery_direction_preliminary`, `direction`, `direction_authority`, `fusion_direction/intent/alignment_score/rule_fired/contradictions`), asymmetry fields, `rr_underlying/rr/rr_confidence/rr_source/rr_flag`, `precor_phase/intent/intent_raw/control`, trend fields, indicators, `macro_regime/active_regime`, scanner/VMS pass-through, `final_discovery_route`, sector/macro-quant columns, options scaffold (`dte` from `_DTE_SCAFFOLD`; expiry/strike/contract_type/bid/ask/premium/iv/ivp = None), plus `horizon_bucket`, `discovery_basis`, `opportunity_label`.
- `discovery_lifecycle_{ts}.csv` — one row per input ticker: `outcome` (SURVIVE/DROP), `lifecycle_state`, `reason_code` (`NO_PRICE_DATA`/`NO_SIGNAL_AT_ANY_HORIZON`/`DISCOVERY_SURVIVOR`), `next_stage`, `horizon_bucket`, `tier`. Hard reconciliation: RuntimeError if outcomes ≠ input count (L2574-2578).
- `early_positions_ultimate_{ts}.csv` (tier 0 only), `final_watchlist_ultimate_{ts}.csv` (tiers 0+1), `discovery_summary_ultimate_{ts}.json`, `run_manifest_ultimate_{ts}.json`.

## A1.4 Core logic (with constants)

**Filters** (`scan_ticker_ultimate`, L1303-1343): `min_bars=30`; price 5–500; `vol20 ≥ 500,000`; options viability: `adv_dollars ≥ 2,500,000`, `ATR14 ≥ $0.40`, `ATR% ≥ 1.0%`. Any failure returns None silently (lifecycle `NO_SIGNAL_AT_ANY_HORIZON`).

**Crabel compression** (`crabel_compression`, L340-424): compression = ATR7/ATR20 of daily range; reject if > `compression_max=0.85`. Base score 65; NR7+vol_ratio<0.8 → 90; NR7 → 75; compression < 0.60 → 85. Percentile bonuses vs own 60-bar history: rank<15 → +10 ("+UltraRare"), <25 → +5 ("+Rare"); vol percentile <25 → +5; capped 100.

**Composite** (L623-631): `wyckoff*0.6 + crabel*0.4` if crabel>0, else wyckoff alone. **Win probability** (L634-643): `clamp(40 + composite*0.25, 35, 75)`.

**State-prior adjustment** (L847-918, table L666-676): MARKUP×RISK_ON +2, ×RISK_OFF +10, ×TRANS +1; ACCUMULATION×RISK_ON −5, ×RISK_OFF +12, ×TRANS +3; DISTRIBUTION×RISK_ON −15, ×RISK_OFF −12, ×TRANS −12. `_LATE_TREND_PENALTY = −8` when trend LATE/EXHAUSTED and regime ≠ RISK_OFF (L881-884). Bounds −20…+15 (L887). Then signal decay −3%/day of bar staleness, cap 20% (L906-916); date-parse failure = `except: pass` (no decay). Phase used for the prior: Wyckoff `current_phase` replaced by precor's `wyckoff_phase` when precor confidence > `phase_evidence_strength` (L1398-1403; repeated L1909-1914 and L555-560).

**VMS adjustment** (L1416-1432): GO & score≥75 → +5; PROBE & ≥60 → +2; WAIT/BLOCK → no change.

**Tier assignment** (`assign_tier`, L587-613): tier1 floor 50, raised to 68 in TRANSITIONAL and 72 in RISK_OFF (demote to 2); tier2 ≥35; tier3 ≥25; else 4 = dropped (L1641-1642). **An `early_signal` forces tier 0 regardless of composite** (L1633-1638) — even a would-be tier 4 survives to the final watchlist.

**Early detection** (`detect_early_position`, L429-582), no Wyckoff phase required: compression slope + ATR14/ATR60 ratio in (0.45, 0.85) → +35; 30-bar range residence [3,15] days → +30; vol_ma5 < 0.85×vol_ma20 → +25; 5-day range <10% → +10; Crabel bonus COILING/CRABEL_READY +15, control BUYERS/SELLERS +10. Qualify: ≥2 base conditions AND score ≥50. Output includes `entry_size 0.33`, `stop_loss = price×0.97`, `days_to_trigger` 3/5/8/10 by compression.

**Evidence-driven phase_align** (L1461-1574): `truth_conf/100×30 + event_evidence/100×25 + phase_evidence/100×20 + event_bonus (15 SPRING/UTAD/SOS/SOW/TEST_OF_SPRING; 8 TEST/LPS/LPSY/SC/BC/UPTHRUST/AR) + recency×15 (≤2d 1.0, ≤5 0.8, ≤10 0.6, ≤20 0.4, else 0.2; unknown 0.5) + trans_score×10`; /100 (max 115); + regime boost RISK_OFF 0.05 / RISK_ON 0.02. Convergence: identical 1.0, adjacent 0.7, diverged 0.4, one-engine 0.6 (L1549-1557).

**lift_proxy_score v3** (L1891-1903, the sort key): `comp_strength×20 + phase_align×20 + regime_align×10 (RISK_ON 0.6/RISK_OFF 0.75/TRANS 0.45) + maturity×12 (EARLY 1.0/DEVELOPING 0.7/LATE 0.2/unknown 0.5) + vol_expansion×10 + sector_lift×6 (LEAD_LONG +1.0…AVOID −1.0 mapped (tilt+1)/2) + vol_abnormality×10 + range_expansion×6 + vwap_acceptance×4 + convergence×2`. An earlier `lift_proxy_score` with different weights (28/19/19/19/9/6) computed at L1619-1627 is **overwritten** at L1891.

**Abnormal repricing** (L1737-1746): `gap×20 + vol×20 + range×15 + vwap_acceptance×15 + dv_z×10 + vol_expansion×10 + ema_aligned(1.0 else 0.3)×10`; EXTREME ≥75 / ACTIVE ≥60 / WATCH ≥45 / NORMAL. `candidate_lane` (L1924-1931): stale → SUPPRESSED; repricing ≥55 & lift ≥40 → HYBRID; repricing ≥60 → REPRICING; else STRUCTURE. Stale = `data_source == STALE_CACHE` or bar age > 5d (L1921).

**Stop/target hierarchy** (L1771-1821): asymmetry gate → Wyckoff stop if within ±25% of price → ATR fallback `price − max(1.5×ATR, 2%×price)`. Target: asymmetry → Wyckoff (validated per direction) → None (`PENDING_OI`). `rr_underlying` = |target−price| / max(price−stop, 0.01); no target ⇒ **fabricates** `R_to_T1 or (3×ATR)/(price−stop)` (L2054-2060). Cap ±50 with `rr_flag` (L2206-2216).

**Horizon** (`assign_discovery_horizon`, L2241-2267): tier 0/1 or trigger STRONG/SINGLE → `1_5d`; tier 2 / composite ≥45 / phase B/C → `6_10d`; tier 3 / ≥30 → `11_20d`; else dropped. **Dead criteria**: reads `wyckoff_phase`/`phase_best`/`trigger_quality` keys that don't exist in the signal dict, so phase/trigger branches never fire — routing is tier/composite only, on the **raw pre-prior** composite (L2255).

**DTE scaffold** (L2229-2238): (tier,phase)→DTE, e.g. (1,'C')=38, (1,'E')=21, default 45. OI overwrites later.

## A1.5 Directional logic (Discovery)

1. `swing_fusion` import failure ⇒ direction from WyckoffEngine only, warning-level (L63-74); per-ticker fusion errors swallowed at DEBUG (L1383-1386) ⇒ `fusion_result={}` ⇒ direction 'NONE'.
2. `fusion_result.get('direction', 'NONE')` (L1375, L1578) — missing key silently NONE.
3. Stage-0 governance (L1576-1583): `preliminary_discovery_direction(fusion_dir, wyckoff_trade_direction)`; comment: "Ambiguity is UNRESOLVED by construction; it must never default to CALL." Emits `discovery_direction_preliminary`, alias `direction`, `direction_authority='DISCOVERY_PRELIMINARY_ONLY'` (L2036-2038).
4. `_reconcile_intent` (L291-335): Rule 1 SELL_SETUP + control BUYERS → TRANSITION; Rule 2 BUY_SETUP + control SELLERS + trend BEARISH → TRANSITION; **Rule 3 SELL_SETUP + trend BULLISH + EMA ALIGNED + ≥40d above EMA50 + ≥25% off 52w low → flipped to BUY_SETUP** (L331-333); only `precor_intent_raw` preserves the original; nothing re-syncs `fusion_direction`/`direction`, so a row can carry `fusion_direction=SHORT` + `precor_intent=BUY_SETUP`. Helper exceptions return neutral ('MIXED'/0/0.0), silently disabling rules 2/3 (L246-247 etc.).
5. `vwap_acceptance_score` (L1689-1709): direction-conditioned; direction not CALL/PUT ⇒ flat 0.5 → feeds 4 pts of lift and 15 pts of repricing regardless of evidence.
6. `repricing_direction` (L1711-1720): CALL/PUT/COUNTER_CALL/COUNTER_PUT/'UNRESOLVED' — explicit UNRESOLVED ✓.
7. `_ema_aligned` (L1733-1736): misaligned/unresolved gets 0.3×10 in repricing.
8. Wyckoff target validation (L1806-1813): for direction NONE a target within ±30% of price is accepted — a directionless target can become `structural_target` and drive `rr_underlying`.
9. Scoring doctrine comment (L1456-1458): "Direction plays no role in any scoring component… Contract selection decides CALL/PUT" — but DISTRIBUTION carries −12…−15 prior in all regimes (L673-675), a de-facto anti-bearish tilt at tier level.
10. `_event_family` (L751-765): SPRING/TEST→BULLISH_REVERSAL, SOS/LPS→BULLISH_CONTINUATION, UTAD/UPTHRUST→BEARISH_REVERSAL, SOW/LPSY→BEARISH_CONTINUATION, unknown→RANGE_NEUTRAL (pass-through only).
11. Scanner direction dropped: discovery copies ~25 scanner fields (L2111-2149) **without** `scanner_direction` — the scanner's directional opinion never reaches the discovery CSV.

## A1.6 Silent failure modes (Discovery)

`adx_14`→0.0 on exception (L181-182); `atr_percentile_rank`→50.0 (L204-205); compression/vol percentile default 50 when <10 obs. `load_bars` (L930-1123): canonical read errors DEBUG-only; Polygon failure → STALE_CACHE fallback returns old bars (L1096-1119); canonical write/observe wrapped `except: pass` (×5). `_bar_days_old_safe`→999. `process_precore_signal` failure → `precor_data=None` at DEBUG (L1352-1354) — crabel bonus/precor phase/transitions/move age silently absent. Regime injection failure → TRANSITIONAL defaults (WARNING). Signal-decay date parsing `except: pass`. `rr` fabrication (L2054-2060). **Duplicate dict key `crabel_score`**: L1959 (compression score, used in composite) silently overwritten at L2022 by precor's score — the CSV reports a different crabel number than the one inside `composite_score`. `signal.update(early_signal)` (L2219-2220): tier-0 rows get structural stop replaced by flat −3% stop and other overwrites.

---

# FILE — `intelligent_orchestrator.py` (6,277 lines, v3.2.1)

## A2.1 Role & invocation

Master conductor. `--evening` (`evening_workflow`, L3708) full pipeline; `--morning`/deprecated `--premarket` (`premarket_workflow`, L5744) live validation. Other CLI: `--run-id`, `--force`, `--data-mode EOD|LATEST`, `--min_universe 1000`, `--target_universe 6500`, `--universe_gate_mode HARD|SOFT|AUTO`, `--universe`, hidden `--cds-startup-self-test`. `main()` sets `AVSHUNTER_STAGE_GATING_ENFORCED` default "1" (L6138) while in-body reads default "0" — gating is ENFORCED via CLI, SHADOW if `evening_workflow()` is called programmatically.

## A2.2 Inputs

`.env` at BASE_DIR (L330-350). `data/universe/polygon_liquid_universe.csv`. Macro `dropbox/macro/macro_intelligence_latest.json` (required fields L1091-1095; `contract_version == macro_contract_v1_0` at pin, L2004-2013; staleness warn >20h). Sidecars: `bond_macro_state.json`, GPT enrichment delta, `catalyst_calendar_latest.csv`. Scanner manifest (max age 24h) + VMS scoreboard + optional signal grades. Hardcoded `C:\Users\ACKVerissimo\vanguard\` for actuarial DB/EV3 caches. Env flags: `AVSHUNTER_STRICT_ACTUARIAL_V6` (default on), `AVSHUNTER_MACRO_CORE_REQUIRED` (default off — macro NOT a hard dependency), `AVSHUNTER_STAGE_GATING_ENFORCED`, `EIL_ADVISORY_ONLY` (default true), `AVSHUNTER_EV3_SHADOW_ENABLED` (on), `AVSHUNTER_MAX_BACKFILL_FAILURE_RATIO` (0.05), `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT` (false), `AVSHUNTER_RUN_KIND`.

## A2.3 Outputs

Per run under `data/output/runs/{run_id}/`: `macro_snapshot.json`, `macro_quant_packet.json`, `truth_packet_run.json`, `run_meta.json`, `scanner_context_{run_id}.json`, `discovery/` CSVs (+`discovery_candidates_cds3_{run_id}.csv` enforced), `packages/*.package.json` (+`eligible_for_trade`), `vanguard/vanguard_signals.csv`, `options/options_intelligence_{run_id}.csv` (+`_phantom_`, `vanguard_signals_enriched_`, `premarket_scope.csv`), `horizon/…` CSVs + summary, `superbrain/superbrain_enriched_{run_id}.csv`, `superbrain/eil_enriched_{run_id}.csv`, `qomega/garch_forecasts_{run_id}.csv`, `execution/execution_v3_5_{run_id}.csv`, `morning_validation/morning_candidates_{run_id}.csv` + `morning_validated_trades_{run_id}.csv`, `intelligence_lab/final_opportunity_book_{run_id}.csv`, `pipeline_integrity_{run_id}.json`, `ev3_shadow/`, `locked_tickers_{run_id}.txt`, audits. Global: `data/output/latest.json`, `runs/latest/`, archive.

## A2.4 Phase sequence (evening), consumers, mutations

Guard: EOD blocked 09:30–16:15 ET weekdays unless `--force`/LATEST (L3739-3782). Then: scanner consumer → preflight (`check_universe`/`check_scripts`/`check_macro_json`; macro absent → `_ensure_runtime_macro_path` writes a **neutral sidecar**, L279) → sector bias map, macro normaliser (FIX-04), bond sidecar merge, enrichment merge — **all rewrite the live macro file in place** → actuarial cache 4.6, transition matrix 4.7 → minimal `scanner_context_latest.json` (L4064-4108) → **Phase 1 Discovery** (abort on failure) → rich scanner context + external intel lane + macro stamp → **Phase 2 quality validation** (abort if candidates <15% of universe, early <1.5%, or tier1+2==0; L1830-1856) → regression detect → position tracker → regime screener → **Phases 5–8 Vanguard** (`pin_run_directory` fail-closed on macro contract → CDS-3 publication → build_packages → inject_macro → backfill (exit-2 tolerated ≤5% failures) → Trap-to-Launch 5.5 → run_vanguard; abort on critical) → Catalyst Truth pre-options, position lock → **Phase 8a Options Intelligence** (abort if returns False; **script missing → returns True** and run continues without options, L2480-2482) → **Phase 1B Horizon Router** (`run_horizon_router(cfg.MACRO_FILE, run_id)` — note: cfg.MACRO_FILE, not the run's pinned macro path, L4208) → horizon patches into OI CSV and vanguard_signals_enriched (also **re-deriving `planned_hold_sessions`**, L2807-2816) → EV-1.5 EV3 shadow + advisory overlay → 8.5 actuarial enrichment → 7.5 Phantom (1200s timeout → bypass) → 8c core intel export → 8.6 trigger layer → packages (`eligible_for_trade` from `triggers.go_eligible`) → **8d SuperBrain passthrough** (`options_verdict → sb_final_verdict`; **column absent ⇒ every row STAND_DOWN**, L2879-2881; NaN spread/contract columns inserted) → 8d-B horizon patch → 8b catastrophe gate (**no-op stub**, L2976-2986) → 8e Wall Break Scorer → FIX-ACTUARIAL-SEQ (inject actuarial into superbrain before EIL; fill <80% → CRITICAL log but continue) → **Phase 9 EIL** (subprocess; requires `sb_final_verdict`; advisory unless `EIL_ADVISORY_ONLY=false`) → actuarial safety-net injection → GARCH + merge (`l3_` fields; merge returns True even on error, L3310-3312) → 8.6b trigger layer → EIL CSV (18 trigger cols + Vanguard governance cols, then enrich) → **handoff conflict guard** (`enforce_handoff_conflict_guard` L5856: execution-like verdicts with EIL BLOCKED/stale/missing trigger/missing Phase-2 baton → overwritten to WATCHLIST/size 0/`capital_permission=NO`, L5928-5935; strict V6 aborts on unresolved conflicts) → 9.5/9B/9C EDE/Kelly/TradeBook **commented out** (PSE inside EIL replaced them) → 9D McMillan advisory → **Phase 10 EOD Candidate Engine** (`build_candidate_manifest` from execution CSV + eil overlay + WBS + discovery + vanguard + horizon; execution CSV missing ⇒ manifest skipped fail-closed but run continues, L5315-5320; then B1 Greeks coalesce — treats `"0"`/`"0.0"` as missing, L5146-5148 — B4 l3 join, McMillan join, macro exposure roles, exit rules) → latest.json/pointers → integrity report (permission ladder L5456-5476 — advisory only) → dropoff/handoff/UAT audits → final manifest + opportunity book → archive/prune/report → Stage 9 outcome capture → run_meta COMPLETED.

Morning (`premarket_workflow` L5744): run_id from CLI else `latest.json`; requires `morning_candidates` or final book; Catalyst Truth pre-validation; `morning_gate.run_morning_gate(run_id, spread_threshold=25.0)`; mandatory `finalize_morning_handoff` (failure fails the workflow).

## A2.5 Directional logic (orchestrator)

1. `MACRO_DIRECTION_SIZING` (L550-558): BULL/RISK_ON {CALL 1.00, PUT 0.25}; TRANSITIONAL {0.75/0.75}; TRANSITIONAL_BEARISH {0.50/1.00}; RISK_OFF/BEAR {0.25/1.00}; unknown {0.75/0.75}. Macro is sizing-only by doctrine (L541-549). `PUT_PERMISSION_VIX_THRESHOLD = 0.0` (deprecated, still published).
2. **Phase 1B silent CALL default** (L1445-1452): `_first_present(row, ["instrument","options_direction","strategy_type","direction"], "CALL")`; sentinel list treats None/""/nan/NONE as missing but **not "UNRESOLVED"** — NONE→CALL; UNRESOLVED passed literally as instrument; discovery's preliminary direction (no post-structure authority) becomes the routed instrument when OI fields are absent.
3. `_phase_d_confirmed` (L1473-1481): true for D/E/PHASE_D/PHASE_E/STRONG/SINGLE/MARKDOWN/DISTRIBUTION — conflates trigger quality and bearish buckets with bullish phase-D confirmation; historically gates PUT permission.
4. `_neutral_macro_payload` (L234-276): missing macro ⇒ every horizon `direction=NEUTRAL, bullish_prob 50, go_no_go=GO_SELECTIVE, size_multiplier 1.0` — **full size, not conservative**.
5. Scanner routing (L762-846): GO/≥75 FULL_PIPELINE; PROBE/≥60 DISCOVERY_ONLY; WAIT/≥45 WATCHLIST_ONLY; grade override C/D/REJECT. But the minimal pre-discovery context (L4075-4100) omits `scanner_primary_route`/`signal_grade_route`, so discovery's `final_discovery_route` defaults every scanner ticker to WATCHLIST_ONLY, and `scanner_direction` is never read by discovery.
6. Passthrough default: `sb_final_verdict="STAND_DOWN"` for all rows when `options_verdict` absent (L2879-2881).
7. Handoff-guard verdict overwrites (L5928-5935) — the only orchestrator-side verdict mutation; audited in `handoff_conflict_flags`.
8. **Ticker-keyed collisions**: `_ticker_to_raw` (L1521, comment admits CALL+PUT collision), `drop_duplicates(subset=["ticker"], keep="first")` fallbacks (L2792-2795), ticker-keyed superbrain patch (L1553-1565), GARCH/B1/B4/McMillan/8.6b joins — dual-direction tickers get one direction's fields applied to both rows or dropped.
9. Unmatched horizon rows default `horizon_bucket="unrouted"`, `horizon_action="UNKNOWN"`, `horizon_size_multiplier=0.0` (L2797-2800).
10. Header-doc horizon bias rules (L62-65): 1-5D GO_SELECTIVE ≥63% bullish_prob; 6-10D GO_REDUCED ≥58% @0.70×; 11-20D MONITOR_ONLY <56%; "PUTS blocked unless VIX>22 AND phase D breakdown confirmed" (thresholds live in `macro_horizon_router.py`, external).

## A2.6 Silent failure modes (orchestrator)

- **Guaranteed UnboundLocalError in `run_horizon_router`'s superbrain patch**: L1574-1575 use `_macro_age_h`/`_macro_ts` first assigned at L1583-1589; exception caught at L1578 → the in-router patch **always fails** and the SPRINT-1 macro-trust fields never reach superbrain_enriched.
- Phase 1B reads `cfg.MACRO_FILE`, not the run's pinned `macro_path` (L4208) — routing can use a different macro view than the rest of the run.
- Macro not a hard dependency by default; missing macro → neutral sidecar (full-size GO_SELECTIVE).
- OI script missing → returns True; OI failure only aborts under CDS enforcement (L2523-2552).
- Phantom timeout → bypass marker (its own write wrapped `except: pass`).
- Broad except-log-continue around: trap engine, catalyst truth ×4, regime screener, actuarial cache/matrix, 8.5, 8.6, 8.6b, GARCH merge (returns True on error), sector guard, McMillan, EOD engine, B1/B4/exposure/exit joins, integrity report, audits, archive, outcome capture, run_meta close. Bare `except: pass` at L160-161, L1148-1149, L1871-1872, L2027, L4448, L4556-4557, L5073-5074, L5429-5430, L5448-5449.
- B1 treats `"0"`/`"0.0"` as missing when coalescing Greeks (L5146-5148) — genuine zeros overwritten.
- `validate_quality` aborts on too FEW candidates (<15% of universe) and instructs "Loosen compression threshold or lower tier minimums" (L1830-1836) — a floor on quantity, opposed to edge scarcity.
- Stale scanner manifest (>24h) silently returns empty. Archive copies every flat `data/output/` file into each run's archive (L3444-3448).

## A2.7 Cross-phase mutations of already-written artefacts

The live macro file rewritten in place ×3 pre-discovery; `options_intelligence_{run_id}.csv` horizon-patched after OI wrote it; `vanguard_signals_enriched` horizon-patched; `superbrain_enriched` created → horizon-patched (re-deriving `planned_hold_sessions`) → actuarial-injected → GARCH-merged; **`eil_enriched` rewritten six times** (EIL write → sector restore → actuarial injection → GARCH merge → trigger injection/enrich → McMillan → handoff-guard verdict overwrite); `execution_v3_5` GARCH- and McMillan-patched post-EIL; `morning_candidates` rewritten by B1/B4/McMillan/exposure/exit passes; discovery `dte` and `direction` superseded by OI but resurface via the Phase-1B fallback chain.


---

# SECTION B — Options Intelligence (Phase 7)

# FILE — `scripts/avshunter_options_intelligence.py` (9,090 lines, "Options Intelligence Layer v1.1")

## B.1 Role & invocation

Position: `Orchestrator → Discovery → Vanguard → [OPTIONS INTELLIGENCE] → Lab` (header L6-7). SuperBrain removed (L825-830); this layer is "the single execution authority" — advisory in practice (`execution_permission` always `MANUAL_REVIEW_REQUIRED`, L295). CLI (L9058-9090): `python avshunter_options_intelligence.py <discovery_csv> <vanguard_csv> [run_id] [output_dir] [max_signals]`. Entry `run_options_layer` (L8317); per-signal `process_ticker(signal_row, macro_context, tle_context)` (L6585). Fed by discovery CSV inner-merged with `vanguard_signals.csv` on `ticker` (L8369); package JSONs supply macro (L531) and TLE trap context (L565). Scope (L8382-8411): tiers 0/1/2 **plus** any Vanguard-supported ticker (verdict TRADE/ACTUARIAL_SUPPORT/ACTUARIAL_MODERATE, or STRONG_EDGE/STRONG quality, or EDGE_STRONG in final_recommendation) regardless of tier; `precor_intent=='WAIT'` excluded unless Vanguard-supported; sorted by composite desc.

## B.2 Inputs

Env: `POLYGON_API_KEY`, `MARKETDATA_API_KEY` (L264-265; silent `.env` fallback L272-290), `AVS_RFR` (0.045), `AVSHUNTER_EV3_MIN_OPEN_INTEREST` (50, defined **never used as filter**, L1220), `AVSHUNTER_EV3_MIN_VOLUME` (unused), `AVSHUNTER_CANONICAL_OFFLINE_REPLAY`, `AVSHUNTER_STAGE_GATING_ENFORCED`, `AVSHUNTER_SECTOR_BIAS_MAP`, `AVSHUNTER_MACRO_CONVICTION`.
APIs — MarketData.app only for options ("No provider fallback is authorised", L1406): chain `GET /v1/options/chain/{T}/` (to today+110d, minOpenInterest=0, mode=cached, L2530-2543; 429 → 60s then 15s waits), exact quotes `/v1/options/quotes/{OCC}/` (L1602), expirations probe, stock candles + quotes. Polygon: reference probe only; options decommissioned (stub returns empty, L2811). CDS: control_plane.sqlite, chain resolver v2/v1, `OptionLiquidityLifecycleStore` (L8432-8524); canonical history bridge for closes. Optional plugins: `iv_engine.py` (L6912), `sector_alignment.py` (L8646); `runs/<run_id>/iv_history.json`.

## B.3 Outputs

`options_intelligence_{run_id}.csv` + `_latest`; `governed_direction_records_{run_id}.jsonl`; `options_candidates_ranked.csv` (rank GO=0…BLOCKED=4 then research score, estimated_R, breakeven feasibility, liquidity); `options_blocked_review.csv`; `contract_rejection_log_{run_id}.csv` (L7880-7890); `vanguard_signals_enriched_{run_id}.csv` (~200 options fields left-joined; unscoped rows `options_verdict='NOT_SCOPED'`, L8935); summaries; `options_session_exceptions_{run_id}.csv`; canonical selected-quote payloads `data/canonical/live_options/...`; CDS SQLite (thesis events, contract observations, selection events).
Key per-row fields: `options_verdict` (EXECUTE/ARMED/STAND_DOWN), `legacy_options_verdict`, `options_route_verdict`/`final_route` (OPTIONS_GO_REVIEW/ARMED_HALF/PROBE_ONLY/EQUITY_ONLY_BETTER/BLOCKED), `options_score` (OIS), `options_research_score`, `confidence_score`, `options_direction`, `options_strategy`, `recommended_contract`, `contract_*`, `stand_down_reason`, `block_code/family/severity/detail`, `alternative_contract_1..3`, `csm_*`, `thesis_id`, `thesis_state`, `liquidity_state`, `morning_transition_state`, `executable_now`, **`data_mode='EOD'` hard-coded on every row (L7419, L7874)**.

## B.4 Stage logic

**Chain fetch/parse**: `fetch_chain` (L2816) CDS v2 → v1 → direct `fetch_chain_md` (L2500). `_normalise_option_quote` (L1495): NEGATIVE/CROSSED ⇒ INVALID; bid=0 & ask>0 ⇒ ONE_SIDED, **mid = ask/2 fabricated** (L1517); TWO_SIDED mid=(bid+ask)/2; spread_pct=(ask−bid)/mid. Keep 0<dte≤110; zero-OI strikes retained. `enrich_contract_with_real_quotes` (L1556) per selected contract; exception ⇒ contract unchanged. **BSM backfills (`backfill_greeks_vectorised` L2205, `backfill_mark_from_bsm` L2289) are dead code — never called (grep-verified).** Heston (L1815-2203) calibration with SIGALRM 3s (Unix-only; on Windows the alarm call raises and is caught, proceeding with whatever result).

**GEX/walls/PCR/velocity**: `compute_gex` (L2877) = sign·gamma·OI·spot·100/strike; flip by interpolation; `compute_gamma_island` (L2919) advisory; `compute_oi_walls` (L3036) call/put walls + max pain; `compute_pcr` (L3056): BULLISH <0.7, BEARISH >1.0; `compute_gamma_velocity` (L3072): IMMINENT ≤2 sessions etc.; **no-history fallback awards IMMINENT/APPROACHING on distance alone** (<1%/<3%, L3126-3133); `compute_volume_confirmation` (L3138) −4…+7; `fetch_sector_regime` (L3215): ~90-ticker ETF map, 5d return thresholds ±1%/±3% — **bug: `closes[min(-5, -len(closes))]` picks the OLDEST close (L3299), so the "5-day" return is the whole-window return**, inflating STRONG_* regimes.

**IV context** `compute_iv_context` (L3616): ATM IV = median IV strikes 0.95–1.05, DTE 10-45; HV30; dual IVP (252d & 30d min-max vs 21d rolling RV), **iv_percentile = max(both)** (L3823); CHEAP only if both ≤0.40, EXPENSIVE >0.65; term structure front(10-25)/back(40-60), BACKWARDATION if front>back×1.02; `compute_iv_skew` (L3446) RR = 25Δput−25Δcall (STEEP_PUT_SKEW >5); `classify_iv_regime` (L3528) UNCERTAIN > EVENT_PRICED > STRUCTURAL_BUILD > COMPLACENT. Fallbacks fabricate: <60 closes ⇒ absolute ladder (branch **crashes** — see B.7); no IV ⇒ iv_engine proxy clamped 20-80, else `iv_rank=50/'FAIR'`. Scanner shortcut (L6712-6753) uses row IV fields with **different label thresholds** (CHEAP≤0.20/EXPENSIVE≥0.70); IV-FIX-002 (L6887-6905) third ladder (≤0.30/>0.70).

**Structural context** `parse_structural_context` (L3880): defaults tier 2, phase 'C', intent 'WAIT', trend 'MIXED', regime 'TRANSITIONAL', **composite 50, win_prob 50** (L3916-3918). Stop only if present & >0 (no fabricated stop). DTE window `DTE_MATRIX[(tier,phase)]` — **only tiers 0/1 have entries; tier 2 always DTE_DEFAULT (14,28,45)** (L1190-1202) — then overridden by horizon `DTE_CONFIG` (1_5d 7-21 Δ0.40-0.60 spr 0.15; 6_10d 21-35 Δ0.35-0.55 spr 0.25; 11_20d 35-60 Δ0.30-0.50 spr 0.35). Hold window by phase A(10,30) B(15,40) C(3,12) D(3,10) E(1,5); urgency IMMEDIATE ≤5/STAGED ≤14/PATIENT. Structural target direction-gated (L4092-4102). Strategy always LONG_CALL/LONG_PUT; delta zones MOMENTUM/COMPRESSION (0.20-0.35), EARLY (0.15-0.30).

**Contract selection** `select_best_contract` (L4368), gates in order: right filter (direction ∉ {CALL,PUT} ⇒ None); DTE strict then relaxed ±15; |Δ| ∈ [0.20, 0.75]; invalid-quote purge; `mark > 0` (OI/volume never hard gates); core delta band (fallback `best_available_suboptimal=True`); target reachability with fallbacks. Empty ⇒ `NO_CONTRACT_PASSED_QUALITY_GATES`/`BLOCK_NO_CONTRACT`, but with chain present the row is re-routed **OPTIONS_PROBE_ONLY with fixed research score 45.0 / confidence 35.0**, `thesis_state='ACTIVE'`, `liquidity_state='CONTRACT_FAMILY_REPAIR_REQUIRED'` + repair alternatives (L6786-6870). Per-contract score (L4494-4533) with fabricated defaults (delta 0.3, theta −0.02, vega 0.05, spread 0.15): `0.30·delta_score + 0.20·dte + 0.20·theta + 0.15·vega + 0.15·liq`; **`spread_limit` computed but never enforced in selection** (hard spread gate only in `derive_verdict` at fixed 25%). Repair selector (L4870) stricter (two-sided quotes, all greeks, strict DTE, spread ≤ horizon max; cap 6). EV3 vertical debit candidates (L5130) research-only.

**Economics** `compute_trade_economics` (L5373): fabricated defaults theta −0.01/vega 0.05/delta 0.35/dte 30/mark floor 0.01; premium = mark×100 (ignores multiplier); breakeven vs **spot** denominator; OVT = pure intrinsic at target; `rr_options = option_gain/mark`; `ev_structural = win_prob·gain − (1−win_prob)·mark` with **win_prob defaulting 50%**; `ev_adjusted = ev_ratio × iv_factor` (1.15 cheap / 0.75 expensive); `theta_drag_pct = |theta|·hold/mark·100`; `vega_risk_pct` = 10-vol-pt loss share.

**Liquidity lifecycle** `_options_liquidity_lifecycle_fields` (L4623): `thesis_id = "{TICKER}:{SIDE}:{evidence_session}:OLM2"`; planned_hold from horizon endpoints 5/10/20; missing inputs ⇒ `DATA_INCOMPLETE`/`LIFECYCLE_DATA_INCOMPLETE`/`CONTRACT_REPAIR`; synthetic mark ⇒ quote_age 901s ⇒ `SYNTHETIC_NOT_EXECUTABLE`; evaluation delegated to `contracts.options_liquidity_lifecycle`. `_ev3_handoff_fields` (L4194): invalidation must be direction-correct else `DATA_DEFECT_WRONG_SIDE`; 7-dim `ev3_barrier_state_key`.

**Thesis persistence & closure ordering** `_persist_options_lifecycle_result` (L7956): terminal immutability — stored terminal thesis overwrites the emitted row (`TERMINAL_THESIS_ALREADY_RECORDED`, executable_now=False); **closure ordering (L8164-8314): ACTIVE observation-capture event first (`TERMINAL_OBSERVATION_CAPTURE`), then canonical dataset + contract observation + selection event, terminal thesis event LAST** (the FLYW fix); degraded THESIS_ONLY_* paths for missing provenance/invalid quote/unsupported enum; v1→v2 legacy supersede; persistence exceptions downgraded to warnings unless stage gating enforced (L8616-8625).

**Research routing** `build_options_research_contract` (L6267): hard vetoes INVALID_CROSSED_QUOTE, DTE_NON_POSITIVE; soft flags (spread>25%, R<1 etc.); info flags (theta>35%, runway<1%, stale/no trigger); top-of-book reconstructed from mid±half-spread when absent (L6326-6334); `expected_move_pct` = **max** of three estimators (L6203-6233) — optimistic by construction; routing ≥75 GO_REVIEW / ≥60 ARMED_HALF / ≥45 PROBE_ONLY / vetoes BLOCKED.

**Convexity/CSM**: `compute_convexity_score_oi` (L949) 8 conditions (C6 vanna neutral-pass when missing; **C8 sector always passes** — see B.7); CONVEXITY_INJECTION all-5-core or ≥6; `compute_time_stop_oi` (L892) 60%/30% of DTE (uses `contract_strike or stock_price` as "spot"; checkpoint text call-shaped even for PUTs); `build_convexity_strike_map` (L7430): BUYABLE requires Δ 0.35–0.55 AND DTE OPTIMAL 5–20 AND runway CLEAR AND EM ≥ breakeven — **conflicts by design with the selection delta zones 0.15–0.35 and DTE matrix minima 14–45**; TRAP |Δ|>0.70 or IVP>75; TOO_LATE ≥60% completed or TLE CHASE; R targets mid×2/4/6/11.

## B.5 Directional logic

1. **`parse_structural_context` L3947-3960 fabricates the Vanguard edge direction** from raw probabilities (`prob_up vs prob_down`) when no explicit edge direction column exists — synthesised opinion feeds arbitration as if Vanguard opined.
2. `structural_direction(intent, trend)` (external `contracts/direction_governance`, L3984): closed fail-closed table → CALL/PUT/STRANGLE/UNRESOLVED. `_direction_from_text` (L3973-3979) defined, never called.
3. `resolve_governed_direction(...)` (external, L3986-4000): consumes preliminary (`discovery_direction_preliminary|direction|fusion_direction`) + row; its `final_direction` becomes **`ctx['direction']` (L4001)** — the single source for the rest of the file; `direction_override_reason` when final ≠ governed.
4. WAIT repair: `vanguard_support_direction_repair` (L4113-4116) — external resolver converts WAIT/non-directional to CALL/PUT on Vanguard support; bypasses the WAIT hard gate (L5857) and earns +4 OIS.
5. Strangle→directional: no in-file conversion; `GOVERNED_NON_DIRECTIONAL_RESOLVED` vs `STRUCTURAL_NON_DIRECTIONAL` + `DIRECTION_RESOLUTION_REQUIRED` gate (L426-441).
6. `_direction_arbitration_oi` (L413): SELL_SETUP + Vanguard CALL ⇒ `CONFLICT_STRUCTURE_LEADS` + gate `VWAP_CONFIRMATION_REQUIRED` — **advisory only; nothing enforces the gate or demotes the verdict; `_ev3_direction_fields` marks the same row RESOLVED (L4295, L4310-4314)**.
7. Hard gates: direction ∉ {CALL,PUT} ⇒ STAND_DOWN, chain suppressed (L6607-6611); `derive_verdict` Gate 1 WAIT (unless repaired) ⇒ `BLOCK_WAIT_INTENT`; Gate 2 NONE ⇒ `BLOCK_NO_DIRECTION`.
8. Direction-gated targets (L4092-4102) — the old both-directions `l1_far > entry` poisoning fixed.
9. Alternative-selector aliasing (L4898-4902): LONG_CALL/BULLISH/BUY/BUY_SETUP→CALL etc.
10. **`compute_convexity_score_oi` is called with the RAW merged row (L7363-7364)** — direction from `signal_row['options_direction'|'direction']`, i.e. the upstream/discovery direction, **not** governed `ctx['direction']`: a second live direction reader in the same output row.
11. PCR vs direction `_direction_conflict_status_oi` (L314): confirm and conflict both carry weight 0.6 — identical confidence weight for confirmation and contradiction; advisory.
12. Macro: `options_macro_alignment_adjustment` (L592) ±3/−2/+1 computed, **never added to OIS** (`options_macro_effective_score_delta` forced 0.0, L6981-6983); nothing inverts direction on macro; PUT gate label only.
13. Sector: OIS ±2/−3 (L5787-5794); EXECUTE→ARMED demotion for PUT vs STRONG_UPTREND / CALL vs STRONG_DOWNTREND (L6052-6060). Trend: +7 aligned, −2 contra (sizing-signal doctrine, L5612-5621).
14. Governed direction effectively locked at parse time; nothing downstream in this file rewrites `ctx['direction']`; full governance record exported per row + JSONL.

Ambiguity behaviours: missing intent ⇒ WAIT ⇒ hard block; missing trend ⇒ MIXED; equal probabilities ⇒ NONE ⇒ NO_PROBABILITY_OPINION; governed STRANGLE unresolved ⇒ chain suppressed; raw-row direction absent at CSM/convexity ⇒ AVOID/0.

## B.6 Scoring & verdict

**OIS** `compute_ois` (L5480), clip 0-100: [0] sample penalties (N<50 −15 / <100 −10 / <200 −5). [A ≈22] IVP ≤0.25 +22 / ≤0.40 +17 / ≤0.65 +10 / else +2 / **unknown +8**; IV/HV <1.05 +5, ≥1.50 −3; regime STRUCTURAL_BUILD +4 / EVENT_PRICED −4 / UNCERTAIN −2; IV RISING +3; skew ±5/±3/−2; CONTANGO +2/BACKWARDATION −2; structurally expensive vol −8. [B ≈22] intent-direction aligned +10 / TRANSITION +5 / WAIT-repaired +4; trend aligned +7 / contra −2 / **other +3**; phase C/D +7, E +5, B +3, A +1; TRANSITIONAL+IVP>0.40 −3. [C ≈22] R:R ≥3 +9 / ≥2 +6 / ≥1.5 +3 / ≥1 +1; flat +2 economics credit (EV advisory, cannot move score, L5660-5669); theta <20% +6 / <40% +3. [D ≈22] flow confirm +8/+3/−4 with **PCR fallback +5/+2/−3 always the active path** (see B.7); gamma velocity +7/+4/−3; wall clearance +5/+2. [E ≈12] Wyckoff volume ≤7/≥−4; vanna +3; sector ±2/−3. [F] no bid AND no ask −8. Macro bonus never applied.

**Verdict** `derive_verdict` (L5823): tiers via `mark_synthetic` (**default True when key missing, L6011** — lenient EOD tier): EOD exec ≥30/armed ≥15; LIVE_LOW ≥35/≥20; FULL_LIVE ≥55/≥25. RR floor for EXECUTE = **1.0 flat** (L6005; the commented 1.5 real-quote floor not implemented). rr<0 ⇒ ARMED; rr<floor ⇒ ARMED. **Score below armed_min ⇒ still ARMED (soft-fail, L6042-6046) — score can no longer produce STAND_DOWN.** Hard gates: WAIT, NO_DIRECTION, `BLOCK_EVENT_PRICED` (**dead — `ctx['near_event']` never set**, L5885-5891), NO_EXPIRY, INVALID_QUOTE, SPREAD >25% (real quotes only), WRONG_STRIKE only when OVT==0 AND mark≤0. Theta >70% warning only. Sector demotions at end. Post-verdict: route BLOCKED ⇒ STAND_DOWN (L7080-7086); `executable_now` false + EXECUTE ⇒ ARMED + PROBE_ONLY (L7087-7101). `options_multiplier = clip(OIS/100, 0.20, 1.00)`; tier multipliers 1.00/0.75/0.50/0.25 (unknown 0.50). `_options_verdict_tier_oi` (L467): READY_EXECUTE / READY_PROBE / STRUCTURE_CONFIRMED_CONTRACT_BLOCKED / WATCHLIST / STAND_DOWN. Research score weights: 0.20 direction_fit + 0.15 liquidity + 0.15 breakeven + 0.15 payoff + 0.10 iv + 0.10 theta + 0.10 runway + 0.05 path; confidence = research − 7.5·|missing|; trigger score computed but excluded from the sum (L6439-6448).

## B.7 Silent failure modes (verified)

1. **`compute_delta_weighted_oi` does not exist** — called at L6705 inside try/except (L6704-6707), neither defined nor imported: institutional-flow confirmation entirely dead; OIS [D] always uses PCR fallback; `dw_*`/`pcr_vol` always None.
2. **`_ivp_label` does not exist** — called at L3794 (<60-closes branch): NameError swallowed at L6757-6763, replacing the whole iv_ctx with all-None defaults (earning the +8 unknown-IVP OIS).
3. Dead BSM backfills; contracts without MD marks simply dropped by `mark>0`.
4. `CAUTION` verdict counted (L8679, L8698) but never produced.
5. **CSM TOO_LATE operator-precedence bug (L7551-7554): for PUTs the row's stop_loss is ignored and the CALL wall is used as the stop**, distorting %-completed and TOO_LATE verdicts on puts.
6. Convexity C8 calls `_flt_conv` on string fields (L1121-1130) — float('STRong…') always excepts ⇒ sector never blocks convexity.
7. Convexity/time-stop/regime-sensitivity run on the raw row (L7362-7365): fields like `theta_drag_pct`/`contract_dte` don't exist there ⇒ components zeroed, convexity computed twice, direction is the upstream one.
8. Sector "5-day" return = whole-window return (L3299).
9. Fabricated defaults: selection (Δ0.3/θ−0.02/vega0.05/spr0.15), economics (θ−0.01/vega0.05/Δ0.35/dte30/mark 0.01), win_prob 50, composite 50, `_derive_eod_spread` (L2468) fabricates bid/ask around mark ±4–10% scaled by OIS (written into contract_bid/ask with `spread_source='OI_DERIVED'`), ONE_SIDED mid = ask/2.
10. Three inconsistent IVP label ladders (0.40/0.65 vs 0.20/0.70 vs 0.30/0.70) + flat 50/'FAIR' default — same vol level can flip CHEAP↔FAIR by data path.
11. `mark_synthetic` default True in verdict tiering lowers the EXECUTE bar to 30 on missing metadata.
12. Dead Gate 4 (near_event never populated).
13. Score-based STAND_DOWN eliminated; gates progressively downgraded (changelog-documented).
14. Broad excepts: .env loader, network `_get`, `_row_f`, `_flt`, macro/TLE loaders, sector fetch, Heston, iv_engine, gamma velocity, sector alignment, CDS setup fallback.
15. Cosmetic f-string crash (L6950-6954): `f"vanna={...:.3f}"` TypeError on None ⇒ "Heston enrichment skipped" printed though enrichment succeeded (the known ~18-row mislabeller).
16. Time-stop checkpoint text call-shaped for PUTs; `contract_strike` used as "spot".
17. Rejection-log horizon defaults `'1_5d'` (L6646, L7922) — rejected rows logged against a window never applied.
18. `options_macro_alignment_note` claims "+3.0 OIS applied" while bonus is forced 0 (L644/745 vs L6982).
19. `trigger_score` excluded from research-score sum.

## B.8 Contradiction observations (this file)

Two live direction sources per row (governed vs raw-row convexity); conflicts surfaced but unenforced and simultaneously marked RESOLVED; flow confirmation dead (PCR noise at ±0.6 weight both ways); gate erosion → nearly everything ARMED; IVP labelling artefacts worth up to 22 OIS points; sector regime overstated then used with two different authorities; CSM contradicts selection by design; macro layer neutered but noisy; `data_mode='EOD'` hard-coded even for live-quoted rows; `expected_move_pct` max-of-three inflates feasibility → intra-row GO-vs-negative-R contradictions. **External dependency to document next: `contracts/direction_governance.py` (structural_direction table + resolve_governed_direction evidence scorer) — not in the reviewed set.**


---

# SECTION C — Wyckoff Engine, Wyckoff/Crabel Precor, and Execution Intelligence Layer

All four files read in full. Here is the structured functional reference.

---

# 1. `WyckoffEngine_3101_v2.py` — Wyckoff Engine v2.1 ("truthful output architecture")

**Path:** `/mnt/user-data/uploads/AVSHUNTER-Intelligence/WyckoffEngine_3101_v2.py` (1096 lines)

## Role / invocation / phase
- Primary Wyckoff phase/event/control classifier for the EOD discovery phase. Called via `WyckoffEngine_3101_v2(min_bars=20).analyze(ticker, bars_df, trend_context)` where `bars` is OHLCV daily bars and `trend_context ∈ {"UP","DOWN","UNKNOWN"}` supplied by the caller.
- Imports canonical enums from `enums_structural` (`ControlState`, `Operator`) — the docstring (lines 11–16) says this exists precisely because the old string values (`BUYERS_IN_CONTROL` etc.) silently failed string comparisons downstream in "fusion/precor", producing `direction=NONE` on valid setups.
- Consumers per comments: `swing_fusion` (reads `truth_confidence`, `contradictions`, `operator`), execution gates (read `phase_evidence_strength`), and the discovery CSV that ultimately feeds the EIL runner (`wyckoff_phase`, `trade_direction`, etc.).

## Inputs / outputs
- Input: a pandas DataFrame with `open/high/low/close/volume`; no files, DB, or env read.
- Output: a flat dict (lines 243–288) — field list under "Emitted fields" below. There is also a `WyckoffOutput` dataclass (47–91) which is **defined but never instantiated**; the dict is the real contract.

## Core logic step by step

**`_prepare_dataframe` (292–317):** computes true range `tr`, 20-bar rolling `vol_avg`/`spread_avg` (min_periods=1), `vol_ratio`, `spread_ratio`, and `poc` = close position within bar (0=low, 1=high, 0.5 if high==low). Wrapped in a **bare `except: return None`** (316–317).

**`_extract_features` (319–367):**
- `range_high/low/width/width_pct` over the **entire** DataFrame passed in (not windowed).
- Boundary touches over last 20 bars: high ≥ range_high×0.98, low ≤ range_low×1.02.
- Break/reclaim over last 10 bars: break = low < range_low×0.98; reclaim = next close > range_low.
- `follow_through_fail_rate` over last 10 bars: up-breakout (close > prev high) that is followed by a lower close.
- `absorption_count` = bars in last 20 with `vol_ratio>1.5 & spread_ratio<0.8` (effort-vs-result).
- `sot_ratio` (shortening of thrust) = mean TR of last 10 / mean TR of the 10 before.

**`_determine_control` (371–419)** — the control engine:
- Absorption bars (vol_ratio>1.5, spread_ratio<0.8): poc>0.7 → buyer +2 each; poc<0.3 → seller +2 each (only counted when `absorption_count>2`).
- Reclaims: buyer += reclaim_count×3.
- follow_through_fail_rate>0.5: seller +2.
- Mean poc of last 20: >0.65 buyer +1; <0.35 seller +1.
- `diff = buyer − seller`: **diff>3 → BUYERS** (conf min(85, 60+3·diff)); **diff<−3 → SELLERS**; **|diff|≤1 → EQUILIBRIUM (conf 65)**; else **SHIFTING (conf 50)**. Note the gap: diff ∈ {2,3,−2,−3} lands in SHIFTING.

**Phase scoring (all independent, no prerequisites):**
- **Phase A** `_score_phase_a` (423–445): climax (max vol_ratio>2.0 & spread_ratio>1.5 → +40; >1.5 & >1.2 → +25); SOT<0.75 → +30; trend_context ∈ {UP,DOWN} → +15 (either direction counts).
- **Phase B** `_score_phase_b` (447–495): range width pct >0.10/+25, >0.05/+15, >0.02/+5; boundary touches (≥3&≥3 +50, ≥2&≥2 +35, ≥1&≥1 +20, one-sided −10); absorption (>3 +25, >1 +15, >0 +10); bar count (≥60 +15, ≥40 +10, ≥20 +5); width<0.015 penalty −20.
- **Phase C** `_score_phase_c` (497–528): break+reclaim → +60 ("classic spring/UTAD"); break only +30; ft_fail_rate >0.7/+35, >0.5/+25, >0.3/+15; narrow bars in last 5 (spread_ratio<0.7): ≥3 +20, ≥2 +10.
- **Phase D** `_score_phase_d` (530–577): price vs range: >high×1.05/+60, ×1.03/+45, ×1.01/+30 (mirror below low); SOT>1.3/+30, >1.1/+20; last-10 monotone trend +25, ≥7 of 9 directional +15 (up or down symmetric).
- **Phase E** `_score_phase_e` (579–597): |move| from bars −30..−20 mean vs current: >15% +50, >10% +30; ≥40 bars +20.

**Phase selection + UNKNOWN gate (137–151):** best phase wins, but if `best_score < 40` **or** `best − second_best < 10` → `current_phase="UNKNOWN"` (evidence strength still = best score).

**Momentum override (156–169):** if chosen phase is C or D, 20-day ROC > 30% **and** close > EMA50 → phase force-reclassified to **B** ("re-accumulation"), note appended to contradictions + warnings. Entire block in `try/except: pass`.

**Event scoring `_score_events` (601–621)** dispatches by phase:
- Phase A (623–651): climax bar (vol_ratio>1.8 & spread_ratio>1.4): down bar → `SC`=70, `PS`=50; up bar → `BC`=70, `PSY`=50; `AR`=65 if a ≥2% reaction within 3 bars.
- Phase B (653–694): low-vol bars in last 10 (`vol_ratio<0.8`): ≥4 → ST=75/Test=70; ≥3 → 65/60; ≥2 → 55/50. Absorption count → `Absorption_Up` **and** `Absorption_Down` at identical scores (70/70, 60/60, 50/50 — deliberately non-directional). TR at 65/55/45 by boundary touches.
- Phase C (696–715): requires `break_count>0`. Control BUYERS → Spring=75, Test=60; SELLERS → UTAD=75, UT=60; **EQUILIBRIUM/SHIFTING → Spring=45 AND UTAD=45** (deliberately below actionable, "no directional coin flip"). Tie broken by dict insertion order → `max()` returns **Spring**.
- Phase D (717–732): close > range_high×1.02 → SOS=70, LPS=50; close < range_low×0.98 → SOW=70, LPSY=50; else empty.
- Phase E (734–742): unconditional `Trend_Continuation`=60, LPS=45, LPSY=45.
- If dict empty → `TR`=40 injected (618–620). If still empty at selection (178–185): `dominant_event="TR"`, evidence 0, confidence 30.

**Confidence (746–795):** phase/event confidence = `35 + min(50, separation)` from next-best; UNKNOWN phase → `min(35, best_raw×0.5)`; single candidate → `min(80, score)`.

**Transition (799–836):** next-phase score > current×0.80 → `progression="towards_next"`, `transition_bias=next phase`, conf `45 + 0.5·gap`; else stable/55. UNKNOWN phase → bias = highest-scoring phase, conf 25, `progression="ambiguous"`.

**Regime conflicts (840–860):** flags only — `trend_context=="UP" & control==SELLERS`, `"DOWN" & BUYERS`, and `phase D & sot_ratio<0.75`. `macro_micro_block = len(conflicts)>0` (284) — documented as flag, not veto.

**Contradictions (937–988):** phase evidence <35; runner-up within 85% of winner; event evidence <35; control SHIFTING; phase B/C with zero absorption. `truth_confidence` (990–1005) = `phase_ev×0.6 + event_ev×0.4 − 10×len(contradictions)`, clamped 0–100.

**`_calculate_wyckoff_score` (931–933):** `phase_ev×0.35 + event_ev×0.35 + control_conf×0.30`.

**`_calculate_levels` (1023–1056):** LONG → stop = 20-bar low×0.98, target = 20-bar high×1.05; SHORT → stop = 20-bar high×1.02, target = 20-bar low×0.95; trigger strings per event.

## DIRECTIONAL LOGIC (this file)
1. **`_determine_trade_setup` (864–891)** — the primary direction assignment:
   - `long_events = ['Spring','SOS','LPS','Test','ST','AR']`, `short_events = ['UTAD','UT','SOW','LPSY','BC']`.
   - Line 873: `LONG` iff event ∈ long_events **and** control ∈ {BUYERS, **EQUILIBRIUM**}.
   - Line 875: `SHORT` iff event ∈ short_events and control ∈ {SELLERS, **EQUILIBRIUM**}.
   - Line 878: else `direction="NONE"` — silent, no reason recorded. Notably `SC`, `PS`, `PSY`, `TR`, `Absorption_Up/Down`, `Trend_Continuation` are in **neither list**, so those events always yield `NONE` regardless of control.
   - Quality (881–889): avg evidence ≥70 Grade_A, ≥55 B, ≥40 C, else Observe.
2. **`_determine_execution_bias` (893–929)** — a **second, independent** direction:
   - avg evidence <35 → `OBSERVE_ONLY`/30 (907–908); range-edge events (Spring/UTAD/UT) outside phase D with phase_ev<40 → `OBSERVE_ONLY`/40 (911–912).
   - Lines 915–923: **bias comes from control alone** — BUYERS → `BULLISH`, SELLERS → `BEARISH`, anything else → `OBSERVE_ONLY`/40. Conf = `50 + 0.5·(avg_ev−50)`; conflicts subtract 25 (floor 20) but never veto (926–927).
   - Consequence: `trade_direction` and `execution_bias` are derived from **different rules** and routinely disagree: event=Spring + control=EQUILIBRIUM → `trade_direction=LONG` but `execution_bias=OBSERVE_ONLY`; event=UTAD + control=BUYERS → `trade_direction=NONE` but `execution_bias=BULLISH`. Two direction fields, two answers, both emitted.
3. **Momentum override (157–169):** re-labels phase, indirectly changing which event family is scored (a Spring/SOS candidate becomes ST/Absorption/TR — often knocking direction to NONE). Silent on exception.
4. **`_infer_operator` (1007–1021):** D/E+BUYERS → MARKUP; D/E+SELLERS → MARKDOWN; A/B/C+BUYERS → ACCUMULATION; A/B/C+SELLERS → DISTRIBUTION; **everything else (EQUILIBRIUM, SHIFTING, UNKNOWN phase) → UNCLEAR** — explicit, not silent.
5. **Ambiguity behaviour:** phase ambiguity → explicit `UNKNOWN`; Phase C directional ambiguity → both Spring/UTAD at 45 (below actionable); direction ambiguity → silent `NONE` (no `UNRESOLVED` marker on the direction field itself).

## Emitted fields consumed downstream
`current_phase` (A/B/C/D/E/UNKNOWN), `phase_confidence`, `phase_evidence_strength` (0–100), `dominant_event` (SC/BC/PS/PSY/AR/TR/ST/Test/Absorption_Up/Absorption_Down/Spring/UTAD/UT/SOS/SOW/LPS/LPSY/Trend_Continuation), `event_confidence`, `event_evidence_strength`, `control_state` (BUYERS/SELLERS/EQUILIBRIUM/SHIFTING), `control_confidence`, `truth_confidence`, `contradictions` (list[str]), `operator` (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION/UNCLEAR), `transition_bias`, `transition_confidence`, `phase_progression` (towards_next/stable/ambiguous), **`trade_direction` (LONG/SHORT/NONE)**, `setup_quality` (Grade_A/B/C/Observe), `wyckoff_score`, **`execution_bias` (BULLISH/BEARISH/OBSERVE_ONLY)**, `execution_confidence`, `entry_trigger`, `stop_loss`, `initial_target`, `regime_conflicts`, `macro_micro_block` (bool flag), `warnings`, `timestamp`.

## Silent failure modes
- Bare `except: return None` in `_prepare_dataframe` (316) → `_error` → `_insufficient_data` (1094–1096): any data-prep exception yields the same output as "not enough bars", with fabricated non-zero values: phase UNKNOWN/conf 25, event TR/conf 25, control EQUILIBRIUM/50, **`transition_bias="B"`** (1077 — a concrete phase hint from no data), wyckoff_score 20, `macro_micro_block=True`.
- Bare `except: pass` around the momentum override (168–169).
- `direction="NONE"` fallthrough (878) with no reason field.

## Observations relevant to contradicting signals
- **Two direction fields with different derivations** (`trade_direction` at 869–878 vs `execution_bias` at 915–923) can and do contradict each other in the same row.
- EQUILIBRIUM control **permits both** LONG and SHORT in `_determine_trade_setup` (873, 875) — direction is then decided purely by which event happened to score highest, incl. dict-order tie-breaks (Phase C tie Spring=UTAD=45 → Spring wins by insertion order, line 712–713; only saved because 45<actionable elsewhere).
- Momentum override (157–169) can flip an engine that had just found a directional Phase C/D setup back to non-directional Phase B — a within-file self-contradiction recorded only as a warning string.
- `_insufficient_data`'s `transition_bias="B"` and non-zero confidences fabricate mild structure from nothing.

---

# 2. `wyckoff_crabel_precor_logic_v2.py` — Wyckoff × Crabel Pre-CORE state machine

**Path:** `/mnt/user-data/uploads/AVSHUNTER-Intelligence/wyckoff_crabel_precor_logic_v2.py` (891 lines)

## Role / invocation / phase
- Declared role (header, lines 5–9): **"AUDIT ENRICHMENT ONLY"** — a secondary data source for discovery; "It does NOT decide direction or intent — that is swing_fusion.py's job." Yet it still computes and emits `intent`/`precor_intent_raw` = BUY_SETUP/SELL_SETUP/etc. (FIX-PRECOR-2, lines 19–23: `intent` is kept "for `_reconcile_intent()` compatibility" in discovery).
- Entry points: `process_precore_signal(ticker, bars)` (884–891, the one discovery uses), `classify_wyckoff_state(bars)` (862–867), `determine_direction_intent(bars)` (870–881). All delegate to a **module-level singleton** `_STATE_MACHINE = WyckoffCrabelStateMachine(lookback=180)` (859).
- Runs on the same OHLCV bars as the Wyckoff engine, in the same discovery phase — so the pipeline carries **two independent Wyckoff readings** per ticker.

## Inputs / outputs
- Input: OHLCV DataFrame (case-insensitive column mapping in `_prepare`, 237–270; trimmed to last 180 bars).
- Output dict (205–230): `wyckoff_phase`, `wyckoff_phase_conf`, `wyckoff_mode` (ACCUMULATION/DISTRIBUTION), `wyckoff_mode_conf`, `control_state`, `control_conf`, `primary_event`, `event_conf`, `crabel_compression_state` (CRABEL_READY/COILING/NONE), `crabel_compression_conf`, `crabel_score` (0–100), **`intent` and `precor_intent_raw`** (WAIT/TRANSITION/BUY_SETUP/SELL_SETUP), `intent_conf`, `transition_to`, `transition_conf`, `move_start_idx`, `move_age_bars`, `notes_top5`, `notes_all`, `_precor_role="AUDIT_ENRICHMENT"`, plus `ticker` (added by `process_precore_signal`).

## Core logic step by step

**Utility helpers (44–96):** `_safe_div`, `_ema`, `_true_range`, `_atr`, `_poc` (NaN → 0.5), `_slope` (normalised linear fit over lookback; 0 if flat/short), `_fractal_swings` (2-left/2-right pivot highs/lows).

**`_prepare` (237–270):** last 180 bars; tr, atr14, poc, vol20/tr20 ratios (inf/NaN → **1.0**), ema21/ema50, ret1, `dir` = sign of close change. Returns None if required columns absent. `analyse` requires ≥50 rows or emits `_output_insufficient`.

**`_infer_control` (301–361):** window = last 30 bars.
- EMA21 & EMA50 slopes both >0 → buyers +2; both <0 → sellers +2.
- EVR absorption: `vol_ratio>1.4 & tr_ratio<0.85` with poc>0.65 → buy count; poc<0.35 → sell count; each ×0.8.
- Failed breakdowns (close<prev low then next close higher) → buyers ×0.7 each; failed breakouts → sellers ×0.7.
- `diff ≥ 2.5 → BUYERS` conf `min(90, 70+6·diff)`; `≤ −2.5 → SELLERS`; `|diff| ≤ 1 → EQUILIBRIUM` 55; else `SHIFTING` 50. **Different thresholds and point weights than the Wyckoff engine's control function** — same tape can yield BUYERS here and EQUILIBRIUM there.

**`_infer_crabel_compression` (368–420)** — the Crabel patterns:
- **NR7**: today's TR is the min of last 7 → +2. **NR4**: min of last 4 → +1.
- **ATR contraction**: atr14 percentile rank within last 40 bars < 0.25 → +2.
- **Inside-bar run**: consecutive inside days from the last bar backwards (up to 5); run ≥2 → +2.
- Total 0–7 → `crabel_score` = score/7×100. **score ≥4 → "CRABEL_READY"/80; ≥2 → "COILING"/72; else "NONE"/50.**
- Note: there is **no ORB (opening-range-breakout) logic** in this file — compression states are the only Crabel constructs; no intraday open data is used.

**`_detect_events` (427–544):** window = last 120, boundaries from last 40 (`rw`):
- **SC/BC** climaxes in last 20 bars of rw: `vol_ratio ≥ 1.8 & tr_ratio ≥ 1.4`; down bar closing off lows (poc≥0.45) → SC conf 78; up bar closing off highs (poc≤0.55) → BC conf 78.
- **Spring**: low < rolling-20 support × (1 − 0.006) then a close back above support within 5 bars → conf 82 (76 if sweep bar vol_ratio<1.0 — "quiet spring").
- **UTAD**: high > rolling-20 resistance × 1.006 then close back below within 5 bars → conf 82/76.
- **SOS**: close > resistance × 1.007 with poc>0.65 and ≥1 of next 3 closes ≥ breakout close → conf 80.
- **SOW**: close < support × 0.993 with poc<0.35 and follow-through → conf 80.
- Sorted by `(idx, confidence)` descending → **most recent event wins as primary**, regardless of type; top 5 kept.

**`_infer_phase` (551–623)** — hierarchy of rules, first match returns:
1. Event overrides: Spring/UTAD → **C** conf `max(75, event conf)`; SOS/SOW → **D** 80; SC/BC → **A** 75 (578–587).
2. `|slope(ema21,30)| > 0.0015 & |ema21−ema50|/close > 0.0015 & dist_from_mid > 0.40` → **E** 78 (593; thresholds deliberately lowered from 0.0025/0.003/0.55 per comment).
3. `|slope| > 0.0010 & |ema_sep| > 0.0010` → **D** 74 (598).
4. `flips ≥ 18 & mid_closes ≥ 18` (direction changes in last 40; closes in middle 40% of 50-bar range) → **B** 76 (603).
5. `tr(10) < tr(prev 20-bar slice)×0.8 & flips ≥ 12` → **A** 72 (610).
6. **Default fallbacks (614–623):** control BUYERS & slope ≥ 0 → **D** 70; SELLERS & slope ≤ 0 → **D** 70; otherwise **B** 45. There is never an UNKNOWN from this path — "always a phase".

**`_infer_mode` (630–651)** — ACCUMULATION vs DISTRIBUTION:
1. Event: Spring/SC/SOS → ACCUMULATION 80; UTAD/BC/SOW → DISTRIBUTION 80.
2. Phase D/E + control BUYERS → ACCUMULATION 74; SELLERS → DISTRIBUTION 74.
3. **Fallback (646–651): sign of 60-bar net return** — `recent_ret ≥ 0` → ACCUMULATION 70, else DISTRIBUTION 70. A drift of +0.01% vs −0.01% flips the mode with confidence 70. No UNRESOLVED option.

**`_map_phase_to_intent` (658–732)** — the phase×mode×event×control×compression → intent table (`precor_intent_raw`):
- **A** → WAIT 75.
- **B** → TRANSITION 75 if compression ∈ {COILING, CRABEL_READY}; else WAIT 72.
- **C** (683–712):
  - Spring & mode ACCUMULATION → **BUY_SETUP 80**; UTAD & DISTRIBUTION → **SELL_SETUP 80**.
  - No decisive event: control BUYERS → **BUY_SETUP 72** (no mode agreement required); control SELLERS **and** mode DISTRIBUTION → SELL_SETUP 72; SELLERS with mode unclear → TRANSITION 70 (asymmetric fix noted at 689–690: SELL requires mode agreement, BUY does not).
  - EQUILIBRIUM + ACCUMULATION → TRANSITION 68; EQUILIBRIUM → TRANSITION 65 (FIX-PRECOR-C-EQUIL, 697–706: previously fell to WAIT and was "misread as SELL_SETUP downstream" — 300/515 Phase-C SELL_SETUPs had EQUILIBRIUM control).
  - SHIFTING → TRANSITION 62; final fallback WAIT 60.
- **D** (714–720): SOS **or** (ACCUMULATION & BUYERS) → BUY_SETUP 78; SOW or (DISTRIBUTION & SELLERS) → SELL_SETUP 78; else TRANSITION 72.
- **E** (723–732): **mode ACCUMULATION → BUY_SETUP 74 with no control check at all** (727–728); DISTRIBUTION & control ∈ {SELLERS, EQUILIBRIUM} → SELL_SETUP 74; **DISTRIBUTION & BUYERS → BUY_SETUP 70 ("mode/control conflict, control wins")** (732).

**`_infer_transition` (739–789):** B→C (75 if pressing a boundary with matching control, else 70); C→D (78 with net_dir≥2 and decisive control, else 70); D→E (75 if |slope|>0.0025 else 70); A→B 75; E→None/0.

**`_estimate_move_start_and_duration` (796–852):** anchors move start to primary event index (FIX-PRECOR-1 coordinate conversion, 807–829) or, in D/E, last fractal swing low (ACCUMULATION) / swing high (DISTRIBUTION); range phases → None/None.

## DIRECTIONAL LOGIC (this file)
- Direction lives in three coupled fields: `wyckoff_mode` (630–651), `control_state` (301–361), and `intent`/`precor_intent_raw` (658–732). Exact rules above. The most important silent defaults:
  - **Line 650–651**: mode = sign of 60-bar drift, conf 70 — a fabricated directional opinion on ambiguous tape.
  - **Line 727–728**: Phase E + ACCUMULATION → BUY_SETUP even when control = SELLERS (SELL_SETUP requires control agreement, BUY does not — a structural long bias).
  - **Line 732**: explicit override "control wins" → BUY_SETUP on a DISTRIBUTION read.
  - **Line 617–621**: default-to-Phase-D rule converts mere control+slope agreement into a trend phase, which then (714–720) converts easily into BUY_SETUP/SELL_SETUP.
- Ambiguity handling: EQUILIBRIUM/SHIFTING in Phase C now explicitly → TRANSITION (not a directional call). No `UNRESOLVED` token exists; the closest is WAIT/TRANSITION.
- `determine_direction_intent()` (870–881) exposes exactly the directional subset (`wyckoff_mode`, `control_state`, `primary_event`, `intent`, `transition_to`) to any caller wanting "just direction".

## Emitted fields read downstream
Listed under Inputs/outputs. Downstream reads confirmed by comments: `intent` → discovery `_reconcile_intent()` / `precor_intent` display column; `crabel_score` → crabel_score CSV column; the EIL runner's EOD enrichment reads a `wyckoff_phase` column from the discovery CSV (see file 4, lines 547, 558–559 — vocabulary mismatch noted there).

## Silent failure modes
- `_output_insufficient` (273–294): **`wyckoff_mode: "ACCUMULATION"`** with conf 0.0 — a bullish-labelled default on no data; any consumer that reads `wyckoff_mode` without checking `wyckoff_mode_conf` inherits a long bias. Also `control_state: "EQUILIBRIUM"`, `intent: "WAIT"`, all confidences 0 (this part honest).
- `vol_ratio`/`tr_ratio` NaN/inf → filled with 1.0 (260–261) — missing volume becomes "average volume", enabling event detection on garbage.
- `_poc` NaN → 0.5 (70).
- Confidences here are hard-coded per rule (70–82 range) — this module retains the confidence-floor style the Wyckoff engine v2.1 removed. Nothing below 45 is ever emitted for phase when data suffices.

## Observations relevant to contradicting signals
- **Two Wyckoff engines, different thresholds, one pipeline**: control (diff≥2.5 with 0.7–2.0-point features here vs diff>3 with 1–3-point features in `WyckoffEngine_3101_v2._determine_control`), phase (rule cascade here vs additive scoring there), and phase defaults (always-a-phase here vs UNKNOWN there). The same bars routinely produce phase/control/mode disagreements between file 1 and file 2, and both sets of fields flow into discovery.
- **Confidence asymmetry**: file 1 emits honest 0–100 (often 35–55); file 2 emits floored 60–82. Any fusion that compares confidences will systematically prefer precor's reading — the opposite of the declared "audit only" role.
- Structural long bias: lines 692 (BUY without mode agreement), 727–728, 732 — three asymmetric rules that resolve ambiguity toward BUY_SETUP.
- `intent` is still emitted under its old name (219) despite demotion, so downstream `_reconcile_intent()` continues to consume a directional opinion this file disclaims responsibility for.
- Primary event = most recent, not strongest (543): one late quiet Spring outranks a strong SOW from a few bars earlier and flips phase (C), mode (ACCUMULATION), and intent (BUY_SETUP) in one shot.

---

# 3. `execution_intelligence.py` — EIL composite engine (S1–S5)

**Path:** `/mnt/user-data/uploads/AVSHUNTER-Intelligence/execution_intelligence.py` (852 lines)

## Role / invocation / phase
- Phase 9 of the pipeline (header, 63–66): "runs after Wall Break Scorer (Phase 8e), before Archive (Phase 10). Operates on all rows passed from superbrain; verdict gates execution."
- Invoked by the runner (file 4) as `build_execution_context_from_row(row, signal_time, check_time, advisory_only)` → `evaluate(ctx)`.
- Delegates the actual per-strategy checks to five external modules (`liquidity_gate`, `iv_distortion`, `gex_flipper`, `obi_predictor`, `poc_timing` — not among the four files); this file builds the context, weights their scores, and forms the verdict.
- Depends on `execution_schema` (weights, thresholds, dataclasses) and optionally `ev_engine_v2`.

## Inputs / outputs
- Input: one `superbrain_enriched` row (dict). Columns read (496–729): `ticker`, `direction`, `sb_final_verdict`/`original_verdict`, `wbs_grade`, `wbs_score`/`wbs`, `underlying_price`/`signal_price`, `contract_occ_symbol`/`recommended_contract`, `contract_premium`/`premium`, `contract_spread_pct`/`spread_pct`/`eil_spread_pct_live`/`bid_ask_spread_pct`/`options_spread_pct`, `contract_iv`/`iv_mid`/`implied_vol`/`iv_rank`, `contract_oi`/`open_interest`, `l3_expected_move_1_5d`/`_6_10d`/`expected_move_10d`, `poc_price`/`structural_target`, `price_vs_poc`, `adx`/`adx_value`, `gamma_flip`, `gamma_flip_gap_pct`, `call_wall`, `put_wall`, `pcr_oi`, `ev2_ev_conf_adj`/`ev2_ev_final`/`ev_final`, `ev2_ev_net`, `ev2_ev_score`, `regime_size_mult`, `l2_bid_size`, `l2_ask_size`, `macro_bias`, `macro_abstain`.
- Output: `ExecutionVerdict` (436–489) — all `eil_*` fields listed below.

## Core logic step by step

**Weights & thresholds (module docstring 69–82 + schema imports):** `S1 Liquidity 0.50, S2 IV 0.40, S3 GEX 0.05, S4 OBI 0.03, S5 POC 0.02`. Verdict: composite ≥85 → `EXECUTE_NOW`; ≥65 → `EXECUTE_WITH_CAUTION`; ≥40 → `EXECUTE_DEFER`; <40 → `STAND_DOWN_MICROSTRUCTURE`; any strategy `block` → `STAND_DOWN_MICROSTRUCTURE` regardless (149–158, 351).

**`evaluate` (330–489):**
1. Runs S1–S5 (344–348). `hard_block = any(r.block)` (351).
2. Weighted composite (354–360).
3. **Macro enrichment modifier (363–381):** `ctx._macro_bias == "CALL_TAILWIND"` → composite **+10**; `"PUT_HEADWIND"` → **−15**; CONTEXT_ONLY/NEUTRAL → 0. Skipped on hard_block. `_macro_abstain=True` only logs (sector headwind bypass); asymmetric penalty (−15 vs +10).
4. `raw_verdict = _composite_verdict(...)` (384). `_hard_execution_gates` (213–230) returns failures **only** for S1 not passed ("no executable market") — spread/IV/GEX were deliberately removed as hard blocks (FIX-HARD-GATES comment 214–223: they "double-penalise and override PSE"). If failures → `final_verdict="BLOCKED"` (389). Otherwise final = raw, and `_hard_execution_gates_advisory` (233–248) appends warnings to `defer_reason` only: spread >20% "[REJECT threshold]", >10% "BORDERLINE" (OTT-02 threshold), `iv_ask_premium>3.0`, `gex_regime=="DAMPENING"`.
5. **`_dynamic_size` (161–188):** start 1.0; composite<70 → ×0.5; S4 failed → ×0.7; `gex_proximity_pct<0.3` → ×0.6; `iv_ask_premium>2.0` → ×0.7; S1 failed → 0.0; × `regime_size_mult` clamped 0–1.
6. `_entry_window_advice` (199–210): S1 verdict WIDE_SPREAD_OPEN/CLOSE/CLOSED_AUCTION → timing advice; **`obi_regime=="BEARISH"` → "Wait for OBI > 0.65 confirmation"** — a directional-flavoured advisory string.
7. EV fields (417–434): `ev_net = ev_raw − live_spread_cost` (spread as decimal); `ev_score = clamp(50 + ev_raw×200, 0, 100)`; `ev_confidence = min(1, composite/100)` — EV confidence is literally the microstructure composite rescaled.

**`_synthesise_gex_map` (255–323) — FIX-03, fabricated dealer positioning:** builds a 3–5-strike GEX map from scalars: call_wall → **+$2.5M**, put_wall → **−$2.5M**, gamma_flip strike → 0 with ±1% anchor strikes at **±$750K**, and current price gets **−$600K if pcr_oi>1.2 / +$600K if pcr_oi<0.8** (neutral in between). These magnitudes are invented constants; S3's flip detection and S4's wall-clearance then "measure" this synthetic structure.

**`build_execution_context_from_row` (496–729):**
- Type-safe accessors `_f/_s/_i/_fnn` (534–561) — every parse failure returns the default silently; `_fnn` treats **0 as missing**.
- `ev_v2_raw` chain (564–569): `ev2_ev_conf_adj → ev2_ev_final → ev_final → 0.0`.
- `regime_size_mult` (575–577): kept unless <0 or >2 (FIX-REGIME-CLAMP: 0 is valid RISK_OFF).
- **Spread resolution (598–624):** first non-zero of 5 column names; >1.0 treated as percent and ÷100; clamped [0.001, 1.0]. **If none: IV-proxy table** — IV<0.20→2.5%, <0.35→4%, <0.55→7%, <0.80→11%, else 18%; if no IV either → **flat 5%** (624). Bid/ask synthesised around `contract_premium` mid (626–631).
- IV bid/ask = mid ×0.97/×1.03 (FIX-04, 642–644). Expected move: percent→decimal (648–654). POC = `poc_price` or `structural_target`; `price_vs_poc` computed if absent (657–660). GEX map via `_synthesise_gex_map` (666–673).
- **Context defaults (676–720):** `superbrain_verdict = _s("sb_final_verdict", _s("original_verdict", "EXECUTE"))` — line 679: **missing verdict silently defaults to "EXECUTE"**. `wbs_grade` default `"POSSIBLE"` (680). **`signal_direction = _s("direction", "LONG")` — line 683: missing/blank direction silently becomes "LONG".** This is the single most consequential silent directional default in the EIL: every direction-aware strategy (GEX runway, OBI regime, POC position) and every downstream reader of the context sees LONG for a row whose direction column was empty/NaN.
- `ctx.regime_size_mult` attached before return (723, FIX-01); `ctx._macro_bias`/`_macro_abstain` from row (726–727).

## DIRECTIONAL LOGIC (this file)
- **Line 683**: `signal_direction` defaults to `"LONG"` — silent, no UNRESOLVED path, no flag emitted.
- **Line 679**: `superbrain_verdict` defaults to `"EXECUTE"`.
- Lines 363–371: macro bias modifier — the only place a directional macro opinion touches the composite; asymmetric (+10/−15) and applied to the score, not the direction.
- Lines 199–210, 246–247: OBI BEARISH / GEX DAMPENING produce advisory text only.
- The five strategies receive `ctx.signal_direction` and score execution quality relative to it; this file never re-derives or overrides direction — it inherits whatever the row says (or LONG if it says nothing).

## Emitted fields consumed downstream
`eil_verdict` (EXECUTE_NOW/EXECUTE_WITH_CAUTION/EXECUTE_DEFER/STAND_DOWN_MICROSTRUCTURE/BLOCKED), `eil_raw_verdict`, `eil_composite_score`, `eil_advisory_only`, `eil_ev_v2`, `eil_ev_net`, `eil_ev_score`, `eil_ev_confidence`, `eil_liquidity_window` (S1 verdict incl. WIDE_SPREAD_OPEN/WIDE_SPREAD_CLOSE/CLOSED_AUCTION), `eil_liquidity_score/passed`, `eil_iv_ask_premium`, `eil_iv_distortion_flag`, `eil_iv_score/passed`, `eil_iv_tailwind_score`, `eil_gex_regime` (NEUTRAL/DAMPENING/…), `eil_gex_flip_level`, `eil_gex_proximity_pct`, `eil_gex_score/passed`, `eil_obi_score_raw` (default 0.5), `eil_obi_regime` (NEUTRAL/BEARISH/…), `eil_obi_score/passed`, `eil_poc_proximity_pct`, `eil_poc_position` (S5 verdict), `eil_poc_score/passed`, `eil_size_multiplier`, `eil_defer_reason`, `eil_recommended_entry_window`, `eil_spread_pct_live`, `eil_check_timestamp`, `eil_schema_version`.

## Silent failure modes
- Missing direction → LONG (683); missing verdict → EXECUTE (679).
- Missing spread → IV-proxy or flat 5% (614–624) — deliberately fabricates cross-sectional variance so the sanity check doesn't fire (comment 613–616: variance is manufactured **to prevent** `SANITY_WARN_SPREAD`).
- Fabricated GEX map with hard-coded dollar magnitudes (289–320).
- `obi_raw` default 0.5 (414, 469); `gex_proximity` default 1.0 (412); all `getattr(..., default)` patterns mean a strategy that fails to set an attribute silently reads as neutral.
- 90% of the composite weight is S1+S2 (0.50+0.40): the "verdict that gates execution" is essentially a spread/IV quality score; structural direction context (GEX+OBI+POC) totals 0.10.

---

# 4. `execution_intelligence_runner.py` — EIL Runner v4.1 (Phase 9 orchestrator)

**Path:** `/mnt/user-data/uploads/AVSHUNTER-Intelligence/execution_intelligence_runner.py` (3609 lines)

## Role / invocation / phase
- CLI-invoked Phase 9 runner (`__main__`, 3193–3605): `--run_id` resolves input `superbrain/superbrain_enriched_{run_id}.csv` and output `execution/execution_v3_5_{run_id}.csv` (3209–3212). It then also writes `superbrain/eil_enriched_{run_id}.csv` (3290–3596), which is what **Morning Validation reads first** (comment 3291–3296).
- Flow: read CSV → spread-column audit (3221–3251) → `apply_vanguard_pre_eil_handoff` (3265) → `run_engine` (3270) → physics fields append, audit contract, truth packets → write execution CSV → merge EIL+WBS+actuarial back into superbrain rows → write eil_enriched.
- `run_engine` (1565–1874): Pass 1 EV computation for all rows, then Pass 2 `_process_row` per row, then frame-level finalisation, defang, capital sanity, distribution sanity.
- Governance state: `LIVE_MODE = True` (433); **PSE retired** (220–234) — `pse_final_size`/`fd_size` are always 0.0, sizing is manual; EV is "advisory only" (436–439). `_EIL_DATA_MODE` = LIVE if `_is_market_hours()` (332–343: approx 09:00–17:00 ET Mon–Fri via crude month-based EDT/EST offset) else `EOD_SYNTHETIC` — **the evening EOD run is always EOD_SYNTHETIC**.

## Inputs / outputs
- Inputs: superbrain_enriched CSV; `{run_dir}/vanguard/vanguard_signals.csv` (2797); `{run_dir}/packages/*.package.json` actuarial maps (3415–3448); `{run_dir}/wall_break_scores_{run_id}.csv` (3465–3484); env `AVSHUNTER_ACCOUNT_RISK_BUDGET` (2413); optional modules `eil_eod_resolver`, `avshunter_monetisation_policy`, `scenario_router`, `probability_engine`, `scenario_builder`, `edge_detector` (all with fallbacks).
- Outputs: `execution_v3_5_{run_id}.csv` and `eil_enriched_{run_id}.csv`. `EIL_COLS` (3306–3392) is the authoritative column list handed downstream — includes every `eil_*`, `pse_*`, `fd_*`, `ev2_*`, scenario, horizon, capital-permission, options-research, and **direction-conflict** field.

## Core logic step by step (every top-level function)

**Import fallbacks (236–311):**
- `derive_probabilities` fallback → scenario_builder (243–247).
- `compute_scenario_probabilities` **inline fallback** (256–267): fabricates `prob_breakout/rejection/drift` from the row's `composite` score alone (pb = min(0.65, 0.25+comp/200), etc.).
- `enrich_vanguard_inputs` fallback (291–311): fabricates `survival_prob = 0.40 + value_acceptance_score×0.40` when missing (307–308); `gamma_obstruction = 1 − control_score`; `path_cleanliness = data_quality_score/100`.
- `_apply_scenario_routing` fallback = identity (279–280).
- `_EIL_TOKEN_NORMALISE` (365–372): EXECUTE_NOW→EXECUTE, EXECUTE_WITH_CAUTION→same, **EXECUTE_DEFER→WATCHLIST**, STAND_DOWN_MICROSTRUCTURE→BLOCKED, BLOCKED→BLOCKED, HIGH_CONVICTION→EXECUTE.

**`_enrich_ctx_for_eod` (462–624)** — EOD synthetic microstructure (called only in EOD mode):
- `_fv` parser strips $/£/,/% (474–496); `_fv_spread_proxy` (498–530): IV table (same as file 3) → else ATR table (atr<2%→3%, <4%→5%, else 9%) → else flat 4%.
- **Synthetic L2 book (539–577):** `liq = 0.4·adx_norm + 0.3·atr_norm + 0.3·vol_norm`, base size 1k–10k. Then a **directional skew**: `is_bull = trend_direction ∈ {UP, UPTREND, BULL} or wyckoff_phase ∈ {MARKUP, ACCUMULATION}`; `is_bear` mirror (558–559). Bull → bid size inflated by up to +30%, ask reduced; bear → reverse. **Two problems:** (a) `wyckoff_phase` in the discovery CSV holds letters A–E (from files 1/2), never MARKUP/ACCUMULATION — that arm can never match (silent vocabulary mismatch); (b) the OBI strategy then reads this book and "detects" imbalance in the direction of `trend_direction` — S4's flow confirmation in every evening run is a restatement of the trend input, not independent evidence.
- OTT-03 quote synthesis (579–606): if `options_mid` missing/≤0, rebuild bid/ask/mid from `contract_premium` + spread.
- S2 IV dispersion (608–624): re-spreads iv_bid/ask from IVP/iv_rank (ask premium 3–8%, bid discount 2–5%).

**Truth model (746–879):**
- `_campaign_verdict` (762–795): fallback chain `campaign_verdict` (if not WATCH/blank) → `sb_campaign` (CORE_CAMPAIGN/CONVEXITY_INJECTION→READY_EXECUTE, STAGED→READY_PROBE, AVOID→REJECT) → `sb_final_verdict` map (EXECUTE→READY_EXECUTE, EXECUTE_WITH_RISK/ARMED→READY_PROBE, STAND_DOWN/DATA_FAILURE→REJECT) → `mv_verdict` map → blank → **WATCH**.
- `_execution_verdict` (798–834): `execution_verdict` (if not SKIP/blank) → `sb_execution_mode` map (FULL/REDUCED→BUY_NOW, PROBE→BUY_SMALL, WAIT→WAIT_RETEST, BLOCKED→SKIP) → `sb_final_verdict` map → `mv_verdict` map → blank → **WAIT_RETEST** ("keeps signal alive", 834).
- `_enrich_truth_fields` (837–879): writes both + provenance defaults (`trigger_source="POLYGON_DELAYED_15M"` etc.), and promotes `signal_type` / `momentum_tier` / `fwd_momentum_conf` from `layer2__`/`actuarial_` prefixes with defaults **NO_EDGE / TIER_4_FLAT / 0.0**.

**Pass 1 (886–940):** `_enrich_row_for_ev` — scenario probabilities, vanguard inputs, scenario routing (writes `scenario_path/size_mult/dte_target/entry_type` from `fusion_alignment_score`), MonetisationPolicy (`mp_*` fields; failure → `mp_hard_block_reason=""` silently, 911–915). `_compute_all_ev` runs `EVEngineV2` per row and writes `ev2_*` + `ev_conf_adj`.

**`_percentile_overrides` (947–952):** retired — always `[False]*n`.

**`_ensure_options_quotes_from_contract` (960–1032):** any-mode quote fallback: if bid/ask/mid all missing/≤0, synthesise from `contract_premium` (+ spread chain, default **0.08**), write `options_bid/ask/mid`, `eil_spread_pct_live`, `options_quote_fallback_applied/source` into the row.

**`_apply_current_edge_hard_veto` (1039–1113):** vetoes capital when `signal_type/pse_signal_type ∈ {NO_EDGE, DATA_MISSING}` or `momentum_tier/pse_momentum_tier ∈ {TIER_4_FLAT, DATA_MISSING}`. Veto → size 0, `fd_verdict=WATCHLIST`, `pse_execution_mode` = EOD_DATA_INSUFFICIENT_REVIEW or, if `physics_verdict ∈ {EARLY_PRESSURE_BUILDING, MONETISABLE_PRESSURE}`, EOD_PROBE_CANDIDATE (forward evidence). Non-veto rows get `capital_permission="EOD_CANDIDATE_ONLY"`.

**`_process_row` (1120–1558)** — per-row Pass 2:
1. Unconditional: `capital_permission="MANUAL"`, `pse_final_size=0`, `fd_size=0`, manual-sizing note (1146–1153).
2. **Horizon gate (1155–1215):** `horizon_action=="MONITOR_ONLY"` → everything zeroed, `fd_verdict=MONITOR_ONLY`, return (router "no longer emits" this — guard retained). `horizon_bucket=="blocked"` → `fd_verdict=BLOCKED`, `pse_execution_mode=FATAL_BLOCK`, return. Default `horizon_size_multiplier`: 6_10d→0.70, blocked/MONITOR→0.0, else 1.0; clamped 0–1.5. Note DEF-HORIZON-EIL comment (1173–1179): blocking on `11_20d` previously killed 13+ valid signals per run.
3. Truth fields + campaign/execution resolution (1218–1220).
4. **EIL call (1225–1397):** build ctx (defaulting direction→LONG per file 3), inject `ev_result.ev_final`, quote fallback, EOD resolver (`_ACTIVE_EOD_RESOLVER.resolve(row)` then ctx **rebuilt** and re-quote-fallbacked, 1266–1299) or local `_enrich_ctx_for_eod`, then `evaluate()`. Writes all `eil_*` row fields (1323–1359); **unknown EIL token → "BLOCKED"** (1323, FIX-2); bond-macro context appended to defer_reason when IV distortion flagged (1342–1354); `eil_spread_pct_live` recomputed from actual ctx (1366–1380). **EIL exception → `eil_v3_verdict="BLOCKED"`, composite 0, size 0** (1382–1390); EIL module unavailable → same with `EIL_UNAVAILABLE` (1391–1397).
5. **PATCH 3 discipline gate (1406–1508):** if campaign==REJECT or execution==SKIP → signal-aware routing: NO_EDGE/TIER_4_FLAT/DATA_MISSING → EOD review modes; STRUCTURAL_MATCH → STRUCTURAL_WATCH; FUTURE_EDGE → FUTURE_WATCH; CURRENT_EDGE/TRANSITION → SKIP with specific reason (MP data block / EIL BLOCKED / no contract / spread>30) else `{SIG}_REVIEW`; genuine campaign REJECT → **FATAL_BLOCK**. Sets `fd_verdict` BLOCK/WATCHLIST, `fd_confidence=90.0`, returns.
6. Manual penalties (1510–1524): WATCH→`pse_manual_penalty=0.5`; READY_PROBE+WAIT_RETEST→0.4; READY_PROBE+BUY_SMALL→0.5; READY_EXECUTE+BUY_NOW→1.0. (Advisory only — PSE retired.)
7. `_apply_retired_sizing_overlay` (2054–2090): zero sizes, all `pse_*_mult=1.0`, and **B3 FIX (2080–2085): `fd_verdict` = `eil_v3_verdict` passthrough** (EXECUTE/EXECUTE_WITH_CAUTION/BLOCKED/WATCHLIST, else WATCHLIST), `fd_confidence=0.0`.
8. Horizon field defaults (1535–1538); veto call 2 (1542); `_apply_signal_authority_policy` (1544); `_finalize_execution_authority` (1545); log line.

**`_apply_signal_authority_policy` (2188–2314):** options-research blocked → OPTIONS_REPAIR_REQUIRED; DATA_MISSING → DATA_REPAIR_REQUIRED; NO_EDGE/TIER_4_FLAT → EOD_PROBE_CANDIDATE (still `capital_permission=EOD_CANDIDATE_ONLY`); STRUCTURAL_MATCH/FUTURE_EDGE → `_apply_eod_candidate_or_watch`; **CURRENT_EDGE in EOD_SYNTHETIC mode failing `_meets_current_edge_clearance` → BLOCKED** (2274–2289); CURRENT_EDGE/TRANSITION otherwise → candidate-or-watch; unknown → WATCHLIST.

**`_meets_current_edge_clearance` (2151–2187):** requires OIS≥55 AND rr≥2.0 AND ivp_label ∈ {CHEAP, FAIR} AND tier ∈ {TIER_2_SUSTAINING, TIER_2_ACTIVE} AND a real (non-synthetic-source) spread.

**`_eod_candidate_profile` (1976–2051):** candidacy requires signal ∈ {CURRENT_EDGE, FUTURE_EDGE, STRUCTURAL_MATCH, TRANSITION} AND **`eil_ok` (eil_v3_verdict ∈ {EXECUTE, EXECUTE_WITH_CAUTION})** AND economics (options route reviewable, or rr≥1.35 & options_score≥20) AND support (options/trigger/catalyst) AND contract seen AND liquidity (spread≤30 or ≤0) AND **`direction_conflict_status != "UNRESOLVED"`** (1993–1994, 2027) AND options research not blocked.

**`_finalize_execution_authority` (2317–2459):** computes `execution_authorized` (needs live capital permission + size>0 + PROBE/EXECUTE mode — impossible under retirement), `eod_candidate_authorized`, `effective_execution_verdict` (MORNING_VALIDATION_REQUIRED for candidates; **BUY_NOW without capital → WATCHLIST**, 2391–2392, with `execution_label_warning`), `pse_suggested_contracts` from kelly×risk_budget/premium (2410–2416), and an **OI_DERIVED spread haircut: confidence_score ×0.875** (2433–2440). `_finalize_execution_authority_frame` (2462–2501) re-applies per-frame with defaults.

**Direction plumbing (2504–2708):**
- `_handoff_side` (2518–2524): maps {CALL, CALLS, LONG_CALL, BULL, BULLISH, UP, BUY}→CALL; {PUT, PUTS, LONG_PUT, BEAR, BEARISH, DOWN, SELL, SHORT}→PUT; **anything else → "" silently** (LONG/NONE/OBSERVE_ONLY from file 1 would map to "").
- **`_direction_arbitration_row` (2536–2562):** option side = **first present** of `canonical_direction, resolved_direction, footprint_direction, direction, primary_direction, options_direction, trade_direction, selected_contract_side`; Vanguard side = first of `vanguard_edge_direction, layer2__edge_direction, vanguard_edge_direction_flat, edge_direction`. No option side → NOT_EVALUATED; no Vanguard side → NO_PROBABILITY_OPINION ("Structure leads"); agree → AGREEMENT; disagree → **CONFLICT_STRUCTURE_LEADS + `direction_conflict_gate="VWAP_CONFIRMATION_REQUIRED"`** — structure always wins, Vanguard never overrides; this is a precedence chain, **not** a weighted scheme (no 4:2 footprint-vs-current weighting exists anywhere in these four files; `footprint_direction` is merely third in the first-present chain).
- `_catalyst_conflict_row` (2565–2587): catalyst side vs option side → CATALYST_CONFLICT_REQUIRES_CONFIRMATION / CATALYST_CONFIRMS / CATALYST_CONTEXT_REVIEW / NO_CATALYST_OPINION.
- **`_ensure_eil_audit_contract` (2590–2708):** fills pcr_vol status fields; then for **all non-BLOCKED rows overwrites `direction_conflict_status`** to `MITIGATED_REQUIRES_CONFIRMATION` (if any structural/catalyst/PCR conflict) or `NO_CONFLICT` (2675–2678); BLOCKED rows → NOT_EVALUATED. This **erases any upstream `UNRESOLVED`** after `_eod_candidate_profile` has already used it — the eil_enriched CSV that Morning Validation reads can never show UNRESOLVED. Builds `direction_conflict_reason`, sets contract_repair fields.

**Vanguard handoff (2711–2868):**
- `_derive_signal_type_from_vanguard` (2747–2761): blank signal+reco → DATA_MISSING; NO_EDGE/NO_ACTUARIAL_DATA → NO_EDGE; n_obs≤0 → NO_EDGE; CONTINUATION → CURRENT_EDGE if `has_edge` or `edge_direction ∈ {CALL, PUT}` else FUTURE_EDGE; STRUCTURAL_MATCH/BROAD_FALLBACK → FUTURE_EDGE (if edge+direction) else STRUCTURAL_MATCH.
- `_derive_momentum_tier_from_vanguard` (2763–2779): raw tier passthrough; else conf≥0.55 & win10≥0.525 → TIER_1_EXPLOSIVE; conf≥0.30 & win10≥0.515 → TIER_2_ACTIVE; conf>0 & n>0 → TIER_3_WATCH; STRUCTURAL/FUTURE with n>0 → TIER_3_WATCH; else DATA_MISSING.
- `apply_vanguard_pre_eil_handoff` (2791–2868): merges vanguard_signals.csv by ticker (missing file → **all rows DATA_MISSING**, 2798–2806), promotes `layer2__*` → flat names incl. `vanguard_edge_direction`, actuarial win rates, `handoff_integrity_status` (OK/VALID_NO_EDGE/ACTUARIAL_MISSING/DATA_MISSING).

**Sanity & defang (2879–3186):**
- `_capital_permission_sanity` (2879–2939): **raises RuntimeError** on any NO_EDGE/TIER_4_FLAT/DATA_MISSING row with live capital permission or positive size.
- `_defang_invalid_campaign_fatal_blocks` (2967–3186): sweeps residual `FATAL_BLOCK/SKIP + CAMPAIGN_OR_EXECUTION_INVALID` rows into signal-aware states (STRUCTURAL_WATCH, FUTURE_WATCH, DATA_REPAIR_REQUIRED, EOD_PROBE_CANDIDATE, OPTIONS_REPAIR_REQUIRED, `{SIG}_REVIEW`), relabels generic SKIPs, downgrades leftovers, corrects OPTIONS_BLOCKED leak rows (3159–3184). Target FATAL_BLOCK <5%.
- Distribution sanity in `run_engine` (1745–1871): execute-rate >95% warn; EOD candidate rate <0.5%/>10% notes; block rate >30% warn; EIL unique verdicts ≤1 → SANITY_FAIL; **frozen strategy scores (std<0.01) → `eil_advisory_only=True` forced on ALL rows** (1823–1837); identical spread std<0.001 → SANITY_WARN_SPREAD; blank MP reasons warn.

**CSV write-back (3290–3596):** merges EIL rows + WBS map + actuarial map into superbrain rows. Display fixes overwrite `ev/ev_conf_adj/ev_final/ev_net` with `ev2_ev_conf_adj` (3506–3526), alias `signal_price` into `current_price/spot_price/underlying_price` (3528–3536), label BSM synthetic premiums (3538–3548). **Lines 3550–3553: `sb_final_verdict` is overwritten with EIL's `fd_verdict` whenever it isn't "BLOCK"** — so the verdict Morning Validation's F1 gate reads is the EIL passthrough verdict, not SuperBrain's own.

## DIRECTIONAL LOGIC (this file) — consolidated
| Location | Rule | Ambiguity behaviour |
|---|---|---|
| 2518–2524 `_handoff_side` | vocab→CALL/PUT | unmapped tokens (incl. `LONG`? — no: LONG isn't in either set unless as LONG_CALL; bare "LONG"/"NONE" → **""** silently) |
| 2536–2562 `_direction_arbitration_row` | first-present column chain; structure > Vanguard, conflict → gate only | explicit statuses (NOT_EVALUATED / NO_PROBABILITY_OPINION / AGREEMENT / CONFLICT_STRUCTURE_LEADS); never re-derives a direction |
| 2565–2587 catalyst conflict | catalyst vs thesis side | explicit statuses |
| 2671–2692 audit contract | rewrites `direction_conflict_status` for active rows | **destroys upstream UNRESOLVED** (silent overwrite) |
| 1993–1994, 2027 candidate profile | `direction_conflict_status=="UNRESOLVED"` blocks EOD candidacy | explicit reason `DIRECTION_CONFLICT_UNRESOLVED` |
| 558–574 `_enrich_ctx_for_eod` | synthesises OBI book skew **from** `trend_direction`/`wyckoff_phase` | wyckoff arm dead (A–E vs MARKUP/ACCUMULATION vocab); neutral rows get spread-scaled noise |
| via file 3 line 683 | ctx direction default LONG | silent |
| 365–372 token map | EXECUTE_DEFER→WATCHLIST; unknown→BLOCKED (1323) | silent verdict downgrade |

## Silent failure modes
- Inline fallbacks that fabricate values: scenario probabilities from `composite` (256–267); `survival_prob` from `value_acceptance_score` (306–308); EOD L2 book, IV dispersion, spread proxies (462–624); quote synthesis default spread 0.08 (1008–1013).
- EIL exception → BLOCKED with composite 0 (1382–1390) — an infrastructure failure becomes a trading verdict (mitigated only by PSE-retirement commentary saying it's a 0.60x penalty, but the row still says BLOCKED).
- MP evaluation exception → `mp_hard_block_reason=""` (911–915) — policy silently inactive per row.
- Actuarial/WBS map load failures → warnings only, columns absent (3443, 3484).
- `fd_confidence=0.0` on all non-gated rows (2086) while gated rows get 90.0 (1493) — confidence semantics inverted for any consumer ranking by it.
- `eil_enriched` write wrapped in a broad `except` that only warns (3604–3605).

## Observations relevant to "contradicting signals / edge lost by the end"
1. **Verdict overwrite at the seam (3550–3553):** `sb_final_verdict = fd_verdict` (unless BLOCK). Since `fd_verdict` is the EIL passthrough (2080–2085) and `EXECUTE_DEFER→WATCHLIST` (368), a SuperBrain EXECUTE regularly leaves Phase 9 as WATCHLIST in the very file Morning Validation trusts — the run's earlier conviction is silently replaced by a microstructure score computed from synthetic evening data.
2. **Evening runs always score fabricated microstructure:** `_is_market_hours` (332–343) makes every EOD run EOD_SYNTHETIC; S1+S2 carry 90% of composite weight (file 3, 69–74) and their inputs (spread, IV bid/ask, L2 book) are synthesised from IV/ATR proxy tables (498–530, file 3 614–624) and the ±3% IV rule. The verdict that overwrites the pipeline's verdict is therefore dominated by invented spreads.
3. **Circular OBI confirmation:** 558–574 skews the synthetic book by `trend_direction`, so S4 "confirms" whatever direction discovery already held — and the `wyckoff_phase ∈ {MARKUP, ACCUMULATION}` test can never match the A–E letters files 1/2 actually emit (silent vocabulary mismatch, same class of bug FIX 2 in file 1 was written to kill).
4. **Silent LONG default** (file 3 line 683) + `_handoff_side` returning "" for `LONG/NONE` tokens (2518–2524): a row whose direction column is blank is scored as LONG by EIL, while direction arbitration simultaneously reports NOT_EVALUATED — two subsystems, two answers.
5. **UNRESOLVED erasure:** `_ensure_eil_audit_contract` (2675–2678) rewrites `direction_conflict_status` to MITIGATED_REQUIRES_CONFIRMATION/NO_CONFLICT for every active row, so the one explicit direction-ambiguity token the candidate gate honours (1993–1994) never survives into the downstream CSV.
6. **Chained re-derivations of verdicts:** `_campaign_verdict`/`_execution_verdict` (762–834) re-derive campaign/execution from up to four different upstream fields with liberal defaults (blank→WATCH / WAIT_RETEST), then PATCH 3, the sizing overlay, signal authority, finalize-authority, and defang each rewrite `pse_execution_mode`/`fd_verdict`/`capital_permission` again — six sequential writers to the same fields per row (1406–1545, 2967–3186), which is precisely the architecture in which end-of-run output contradicts start-of-run intent.
7. **Cross-engine disagreement is structural**: file 1 and file 2 both classify phase/control/direction from the same bars with different thresholds and confidence regimes (file 2 floored 60–82 vs file 1 honest 0–100), and file 2 still emits `intent` despite its "audit only" charter (line 219) — three directional opinions (`trade_direction`/`execution_bias` from file 1, `intent` from file 2, `vanguard_edge_direction` from the handoff) enter arbitration where "structure leads" by column order (2537), not by evidence weight.
8. **Frozen-score fallback flips authority silently:** if the synthetic enrichment still yields flat scores, all rows are force-marked `eil_advisory_only=True` (1832) — the same run can oscillate between EIL-binding and EIL-advisory depending on data availability, changing how downstream convergence treats identical signals.
9. The requested "footprint vs current-signal 4:2 weighting" does **not** exist in these four files; the only weighting schemes present are Wyckoff 0.35/0.35/0.30 (file 1, 933), truth 0.6/0.4 (file 1, 1001), EIL 0.50/0.40/0.05/0.03/0.02 (file 3, 69–74), EOD liquidity 0.4/0.3/0.3 (file 4, 553), and the ±10/−15 macro modifier (file 3, 367–370). If a 4:2 footprint scheme exists it lives in `swing_fusion.py` / discovery, which these files reference but do not contain.

---

# SECTION D — Vanguard Layer 1 (Auction), Layer 2 (Statistical), and EV Engine v3

# Vanguard Layer (Phase 6) + EV Engine v3 — Functional Reference Brief

All paths under `/mnt/user-data/uploads/AVSHUNTER-Intelligence/`. Line numbers refer to the files as read.

One correction to the brief's premise up front: **`behaviour_state_hash` does not exist anywhere in these eleven files.** It is only referenced in `execution_intelligence_runner.py:2713` (as a *required* Vanguard-handoff column) and passed through as context in `scripts/avshunter_options_intelligence.py:4161-4165, 7164-7165` — it is never computed in the Vanguard layer itself. What these eleven files actually contain is **four distinct, mutually inconsistent state identities**: (1) `state_hash` — an MD5 of 9 dims (`state_calculator.py:851-895`), (2) `state_v2` — a 6-dim pipe string (`state_calculator.py:223-227`), (3) the actuarial match key — up to 10 named-column equality dims (`actuarial_query.py:17-32`), and (4) the EV3 `state_key` — a 7-dim pipe string (`ev3_stage0.py:26-34`). None of the four share the same dimension set. Details per file below; the cross-file implications are in the closing observations.

---

## LAYER 1 (AUCTION)

## 1. `vanguard/layer1_auction/market_profile.py` (292 lines)

**Role.** Builds a TPO Market Profile per session. Invoked only by `AuctionStateSynthesizer.synthesize()` (one profile per trading date, plus a fallback single profile). Consumes an OHLCV DataFrame; produces a `MarketProfile` schema object consumed by `value_acceptance`, `value_migration`, `auction_synthesizer` scenarios, and `state_calculator` (POC positioning).

**Inputs.** `bars` DataFrame with `timestamp, open, high, low, close, volume` (intraday). Config: `MARKET_PROFILE_CONFIG['tpo_interval_minutes'|'value_area_percent'|'min_bars_for_profile']` (lines 28-30). Note `tpo_interval` is loaded but **never used** — the TPO count treats whatever bar granularity arrives as one "letter" each.

**Outputs (`MarketProfile`).** `poc: float`, `value_area_high`, `value_area_low`, `profile_type ∈ {NORMAL, P_SHAPED, B_SHAPED, TREND, UNKNOWN, INSUFFICIENT_DATA}`, `balance ∈ {BALANCED, BUYER_DOMINATED, SELLER_DOMINATED, UNKNOWN}`, `tpo_distribution: Dict[price→count]`, `timestamp`, `timeframe`.

**Core logic.**
- `calculate_profile` (32-81): if `bars is None or len < min_bars` → `_empty_profile` with `poc=0.0, VA=0.0/0.0, profile_type="INSUFFICIENT_DATA"` (279-292).
- `_build_tpo_distribution` (83-116): **bin size is a hard-coded `price_increment = 0.10`** (line 95) regardless of ticker price. Each bar's `[floor(low/0.10)*0.10, ceil(high/0.10)*0.10]` range increments every $0.10 level it spans by 1. Not volume-weighted — pure time/TPO count.
- `_find_point_of_control` (118-128): `poc = max(tpo_counts, key=count)`; ties resolved by dict iteration order (arbitrary). Returns `0.0` on empty.
- `_calculate_value_area` (130-187): accumulate 70% (`value_area_percent`) of total TPO starting at POC, expanding **one $0.10 level at a time** toward whichever adjacent level has more TPO (ties expand up, line 177). Not the textbook two-row TPO method, but deterministic.
- `_classify_profile_type` (189-238): computes `pct_above/pct_below` POC and `va_ratio = VA width / full range`. Rules: `|pct_above−pct_below| < 0.15` → `NORMAL` if `va_ratio > 0.60` else `TREND`; `pct_below > pct_above + 0.20` → `P_SHAPED` (comment: "rejected lower prices – bullish", line 198/234); `pct_above > pct_below + 0.20` → `B_SHAPED` ("bearish"); else `NORMAL`.
- `_assess_balance` (240-277): ignores the profile entirely; heuristic on the raw session: `close_position = (close−low)/(high−low)`; `> 0.70` and `price_change_pct > +1%` → `BUYER_DOMINATED`; `< 0.30` and `< −1%` → `SELLER_DOMINATED`; else `BALANCED`. `< 5 bars` → `UNKNOWN`.

**Directional logic.** `profile_type` carries the file's only directional labels (P/B shaped, lines 233-236) and `balance` (272-277). **Neither is consumed anywhere in the other ten files** — no downstream reader of `profile_type` or `balance` exists in this set. Directional content of this file that *is* consumed downstream: `poc`, `value_area_high/low` (used as long-side triggers and stops).

**Silent failure modes.**
- `_empty_profile` sets `poc=0.0` and `VA=0/0` (283-286). Downstream, `value_acceptance._classify_position_in_profile` (97-114) then always returns `ABOVE_VALUE` (any positive price > 0.0), i.e. **missing profile data silently reads as "price above value"**, and `auction_synthesizer._assess_conditional_near` line 251 (`current_price < profile.poc` is False) skips the POC-reclaim trigger.
- Fixed $0.10 bin: on a $3 stock the whole day collapses into a handful of bins (VA ≈ whole range → `NORMAL`); on a $900 stock thousands of near-empty bins (VA narrow → `TREND`). Profile-type and VA statistics are therefore **price-level dependent**, not structure dependent.
- `timestamp` fallback `pd.Timestamp.now()` (line 79).

---

## 2. `vanguard/layer1_auction/auction_synthesizer.py` (442 lines)

**Role.** Orchestrates all Layer 1 modules into an `AuctionVerdict`. Entry: `AuctionStateSynthesizer.synthesize(vanguard_input)`. Consumed by `state_calculator.calculate_state` and `edge_detector.detect_edge` (and Layer 3 scenario builder via `auction` argument).

**Inputs.** `VanguardInput`: `ticker`, `current_price`, `technical.ohlcv` (must contain a `date` column for multi-session split), `technical.volume_profile`, `microstructure.time_and_sales`. Config: `AUCTION_VERDICT_THRESHOLDS` (`ready_min_control_confidence`, `ready_allow_choppy_migration`), `SCENARIO_PROBABILITIES`.

**Outputs (`AuctionVerdict`).** `ready_to_trade: bool`, `confidence: float`, `auction_state ∈ {ALIGNED, TRANSITIONING, SEARCHING, CONFLICTED}`, `profile`, `acceptance`, `control`, `migration`, `scenarios{immediate, conditional_near, conditional_far}`, `reasoning: str`.

**Core logic.**
- Session split (56-80): `bars.groupby('date')` → one `MarketProfile` per session, in **ascending date order** (pandas groupby sorts keys), stored in `profiles` (line 67); most recent used as `profile` (line 70). Fallback: single profile if no `date` column.
- Migration call (100-103): `track_migration(profiles=profiles ...)` — passes the **chronologically ordered** list. See file 5 for why this inverts the migration direction.
- `_generate_scenarios` (129-161) builds three scenarios:
  - `_assess_immediate_scenario` (163-231): `probability = aggressive_base_probability` + `prob_boost` for each of: `acceptance.score ≥ 50`; `control.controller ∈ {BUYERS, SELLERS} and confidence > 0.60`; `migration.direction != "SIDEWAYS" and consistency.startswith("CONSISTENT")` (line 198). Feasibility: `score < 30` → infeasible/`POOR`; `≥ 50` → `MEDIUM/FAIR`; else `FAIR`. Risk level counts risk_factors (214-221). Probability capped at `max_probability`.
  - `_assess_conditional_near` (233-285): trigger identification — if `current_price < profile.poc` → "VWAP/POC reclaim" (POC used *as a proxy for VWAP*, line 251); if `position_in_profile == BELOW_VALUE` → "Value Area entry"; **bug at 261-265**: the control branch unconditionally overwrites `trigger_price` — if control ≠ NEUTRAL, `trigger_price = current_price * 1.02` replaces any structurally derived trigger, while `triggers[0]` still names the structural trigger; and line 282 uses a `'trigger_price' in locals()` guard. Probability: `moderate_base_probability` + boost for `acceptance.score ≥ 40` and `control.confidence ≥ 0.55`.
  - `_assess_conditional_far` (287-326): trigger = `value_area_high * 1.02` ("Breakout above VAH+2%"), fallback `current_price * 1.05` if VAH==0. Probability: `conservative_base_probability` + boosts (`score ≥ 50`, `confidence ≥ 0.65`).
- `_determine_verdict` (328-441). Three gates:
  - Gate 1 (346-351): fails only if `acceptance.classification == "TOLERATED"`. **`"INSUFFICIENT_DATA"` (score −1) passes the gate** and is logged as a *favorable* factor "Value INSUFFICIENT_DATA".
  - Gate 2 (354-359): fails if `controller == "NEUTRAL" and confidence < ready_min_control_confidence`.
  - Gate 3 (362-365): fails if `migration.consistency == "CHOPPY"` and choppy not allowed. `UNKNOWN`/`MIXED` consistency **passes**.
  - State (369-391): 0 failed → `ALIGNED`, `ready=True`, `confidence = min(acceptance.score/100, control.confidence) * 0.8` (line 373 — with score −1 this becomes **negative confidence −0.008**); 1 failed → `TRANSITIONING`, conf 0.5; 2 → `SEARCHING`, 0.3; 3 → `CONFLICTED`, 0.1.

**Directional logic.**
- All three scenarios are **long-only framed**: POC reclaim, VA entry from below, breakout above VAH (+2%), `current_price * 1.02/1.05` upside triggers (251-307). There is no bearish scenario construction even when `control.controller == "SELLERS"`. On ambiguity the scenarios silently stay bullish.
- `auction_state` itself is direction-neutral but is a gate/score input to `edge_detector` (Gate 1 CONFLICTED veto; right_side_score +25/+15/+5).

**Emitted fields read downstream.** `auction_state` (edge_detector Gate 1, `_calculate_right_side_score`; state_calculator `StateVector.auction_state`), `confidence` (edge_detector `_calculate_confidence` 40% weight; state_calculator confidence boost), `acceptance.score/classification/position_in_profile`, `control.controller/confidence`, `migration.direction/speed/consistency`, `profile.poc/VA` (scenario_builder stops/targets), `reasoning` (embedded in rationale text).

**Silent failure modes.** INSUFFICIENT_DATA passing Gate 1 as favorable (346-351); negative confidence path (373); trigger_price overwrite (261-265); when only one session exists migration is `[profile]` → `UNKNOWN` migration which passes Gate 3.

---

## 3. `vanguard/layer1_auction/control_identifier.py` (388 lines)

**Role.** Determines `BUYERS`/`SELLERS`/`NEUTRAL` tape control. Invoked by synthesizer step 3. Output `ControlState` consumed by acceptance-free scenario logic, `_determine_verdict` Gate 2, `state_calculator` (`control_state`, `control_confidence`), `edge_detector._determine_direction` (±40 pts — largest single directional weight in the system).

**Inputs.** `recent_bars` OHLCV; optional `time_and_sales` with `aggressor ∈ {BUY, SELL}`, `price`, `bid`, `ask`, `size`. Config: `CONTROL_THRESHOLDS` (`aggression_buyer_threshold`, `aggression_seller_threshold`, `volume_trend_acceleration`, `control_strong_threshold`).

**Outputs (`ControlState`).** `controller ∈ {BUYERS, SELLERS, NEUTRAL}`, `confidence ∈ [0.5, 1.0]`, `aggression: AggressionMetrics` (`interpretation ∈ {BUYERS_AGGRESSIVE, SELLERS_AGGRESSIVE, BALANCED, UNKNOWN}`), `efficiency: EfficiencyMetrics` (`driver ∈ {BUYERS, SELLERS, NEUTRAL}`), `trend: VolumeTrend` (`interpretation ∈ {BUYERS_ACCELERATING, SELLERS_ACCELERATING, STABLE, UNKNOWN}`), `interpretation: str`.

**Core logic.**
- Aggression (72-169): T&S path — `buy_aggressive = Σ size where aggressor==BUY and price ≥ ask`; `sell_aggressive = Σ size where aggressor==SELL and price ≤ bid`; classify vs config thresholds. **Bar fallback** (136-169): green-bar volume = buying, red-bar volume = selling (doji bars dropped); `buy_pct > 0.60` → `BUYERS_AGGRESSIVE`, `sell_pct > 0.60` → `SELLERS_AGGRESSIVE`, else `BALANCED`. Empty bars → `UNKNOWN` with 0.5/0.5.
- Efficiency (171-214): whole-window close-to-close change; `price_change_pct > +0.5%` → driver `BUYERS`; `< −0.5%` → `SELLERS` (score made positive, line 205); else `NEUTRAL`. `efficiency_score = price_change_pct / (volume/1M)` — computed but never used in the control decision.
- Volume trend (216-302): first-half vs second-half buy/sell volume growth; T&S path uses `volume_trend_acceleration` threshold (252); bar fallback hard-codes `0.20` (291-293). `< 10` rows → `UNKNOWN`.
- `_determine_control` (304-367): point-split — Aggression 40 pts, Efficiency 35 pts, Trend 25 pts to the winning side; **neutral/balanced outcomes split points 50/50** (20/20, 17.5/17.5, 12.5/12.5). `buyer_pct = buyer_points/100`. Classification (352-360): `buyer_pct > 1 − control_strong_threshold` → BUYERS with `confidence = buyer_pct`; `buyer_pct < control_strong_threshold` → SELLERS with `confidence = 1 − buyer_pct`; else NEUTRAL, confidence fixed 0.5.

**Directional logic.** The controller is the primary CALL/PUT driver downstream (`edge_detector.py:505-508`, ±40×confidence). Because efficiency is 35/100 points and is just *sign of recent price change*, control substantially **restates recent price direction** — a down-drifting name in accumulation reads SELLERS. On ambiguity: all-neutral components → buyer_pct exactly 0.5 → `NEUTRAL`/0.5 (silent neutral, not an insufficient-data flag; `UNKNOWN` sub-metrics are treated identically to `BALANCED`/`STABLE` in the scoring at 321-345 — the else branches catch them).

**Silent failure modes.** No-data path returns plausible NEUTRAL 0.5 rather than an explicit insufficient marker (142, 180-185, 273); bar-color aggression proxy silently substitutes for T&S whenever T&S is None/empty (82-85) with no flag on the output; hard-coded 0.60 / 0.20 fallback thresholds diverge from configured T&S thresholds.

---

## 4. `vanguard/layer1_auction/value_acceptance.py` (453 lines)

**Role.** Scores whether the current price is ACCEPTED vs TOLERATED ("the critical filter that blocks 80% of trades", line 8). Invoked by synthesizer step 2. Output `AcceptanceState` consumed by synthesizer gates/scenarios, `state_calculator` (`value_acceptance_score`, `position_in_value`, structure quality), edge_detector (via `state.value_acceptance_score` into EVEngineV2 `composite`), scenario_builder probability boosts.

**Inputs.** `current_price`, `MarketProfile`, `volume_profile` DataFrame (`price_level, volume, buys, sells`), `recent_bars`, optional T&S. Config `ACCEPTANCE_THRESHOLDS` keys used: `volume_high_threshold`, `volume_normal_threshold`, `time_extended_bars`, `time_moderate_bars`, `flow_balanced_min/max`, `flow_slightly_imbalanced_min/max`, `participants_diverse_threshold`, `participants_moderate_threshold`, `acceptance_score_accepted` (docstring 75), `acceptance_score_transitioning` (docstring 50).

**Outputs (`AcceptanceState`).** `level`, `score ∈ {−1.0} ∪ [0,100]`, `classification ∈ {ACCEPTED, TRANSITIONING, TOLERATED, INSUFFICIENT_DATA}`, `position_in_profile ∈ {INSIDE_VALUE, ABOVE_VALUE, BELOW_VALUE}`, plus component qualities (`VolumeQuality.quality ∈ {HIGH, NORMAL, LOW, UNKNOWN}`, `TimeQuality.quality ∈ {EXTENDED, MODERATE, BRIEF, UNKNOWN}`, `FlowBalance.quality ∈ {BALANCED, SLIGHTLY_IMBALANCED, IMBALANCED, UNKNOWN}`, `ParticipantQuality.quality ∈ {DIVERSE, MODERATE, CONCENTRATED, UNKNOWN}`).

**Core logic.**
- Position (97-114): VA containment test. With an empty profile (VA=0/0), any price → `ABOVE_VALUE` (silent).
- Volume at price (116-163): ±0.5% band volume vs mean volume-per-level; relative > `volume_high_threshold` → HIGH etc.
- Time at price (165-199): count of bars overlapping ±0.5% band vs `time_extended_bars`/`time_moderate_bars`.
- Flow balance (201-318): T&S path uses configured band on `buy_ratio`; bar fallback (268-318) uses ±1% band and hard-coded bands `0.45–0.55` BALANCED / `0.40–0.60` SLIGHTLY_IMBALANCED / else IMBALANCED; no bars near price → UNKNOWN (293).
- Participants (320-362): proxy = `nunique(size)` in ±0.5% band vs thresholds; no T&S → UNKNOWN.
- Score (364-430), weights Position 30 / Volume 25 / Time 20 / Flow 15 / Participants 10:
  - **FIX 4 fallback detection** (385-394): returns sentinel `−1.0` only when `volume ∈ {UNKNOWN, LOW}` AND `time ∈ {BRIEF, UNKNOWN}` AND `flow == UNKNOWN` AND `participants == UNKNOWN`. Otherwise UNKNOWNs get **partial credit**: volume UNKNOWN=10, time UNKNOWN=5, flow UNKNOWN=5, participants UNKNOWN=3 (405-428). `INSIDE_VALUE`=30, `ABOVE_VALUE`/`BELOW_VALUE`=10 each — position outside value scores identically regardless of side (399-402), so acceptance carries no directional information.
- Classification (432-453): `score < 0` → `INSUFFICIENT_DATA`; `≥ 75` → ACCEPTED; `≥ 50` → TRANSITIONING; else TOLERATED.

**Directional logic.** None directly — but the score is a probability booster in scenarios (`≥ 40/50` thresholds) and 40 pts of structure quality in state_calculator; it therefore *modulates* directional confidence without carrying direction.

**Silent failure modes.**
- The −1 sentinel rarely fires when bars exist: bar-estimated flow is usually not UNKNOWN, so a nearly-data-free evaluation still yields e.g. `INSIDE_VALUE + all-UNKNOWN partial credits = 30+10+5+5+3 = 53 → TRANSITIONING` — a **fabricated mid-grade acceptance from no microstructure data**.
- When the sentinel does fire, downstream handling is inconsistent: synthesizer Gate 1 treats `INSUFFICIENT_DATA` as a pass (see file 2), and `score=−1` propagates into `StateVector.value_acceptance_score` (`state_calculator.py:258`) and into EVEngineV2 `composite` (`edge_detector.py:275`).

---

## 5. `vanguard/layer1_auction/value_migration.py` (223 lines)

**Role.** Classifies multi-session value-area migration. Invoked by synthesizer step 4. Output `MigrationState` consumed by: synthesizer Gate 3 and immediate scenario; `state_calculator` (`value_migration_direction/speed`); **`edge_detector._determine_direction` (±30/±15 pts)** and `_calculate_right_side_score` (+15/+10); scenario_builder probability boosts (`value_migration_direction != "SIDEWAYS"`).

**Inputs.** `profiles: List[MarketProfile]` — docstring line 34: "**most recent first**". Config `MIGRATION_THRESHOLDS`: `migration_significant_percent`, `migration_fast_daily_percent`, `migration_moderate_daily_percent`.

**Outputs (`MigrationState`).** `direction ∈ {UP, DOWN, SIDEWAYS, UNKNOWN}`, `speed ∈ {FAST, MODERATE, SLOW, UNKNOWN}`, `consistency ∈ {CONSISTENT_UP, CONSISTENT_DOWN, TRENDING_UP, TRENDING_DOWN, MIXED, CHOPPY, UNKNOWN}`, `magnitude: float`, `interpretation: str`.

**Core logic.**
- `< 2` profiles → all-UNKNOWN `_no_migration_available` (41-42, 213-223) — explicit insufficient-data path.
- `_extract_migration_metrics` (73-104): `poc_change = (poc_series[0] − poc_series[-1]) / poc_series[-1]` (line 84), same for VA high/low/mid; `total_change` = mean of the four; `daily_changes[i] = (poc[i] − poc[i+1]) / poc[i+1]` (93-96). **All formulas assume index 0 is the newest session.**
- Direction (106-120): `total_change > migration_significant_percent` → UP; `< −threshold` → DOWN; else SIDEWAYS.
- Speed (122-140): `|total_change| / num_sessions` vs fast/moderate daily thresholds.
- Consistency (142-187): up-day ratio `≥ 0.80` → CONSISTENT_UP; `≥ 0.60` → TRENDING_UP (mirror for down); else CHOPPY if `std(daily_changes) > 2×|mean|` else MIXED.

**Directional logic + the critical defect.** `auction_synthesizer.py:61-67` builds `profiles` by `groupby('date')` in **ascending chronological order** (oldest first) and passes the list unmodified (100-103). With oldest-first input, `poc_series[0] − poc_series[-1]` = oldest − newest, i.e. **the sign of `total_change`, of every `daily_change`, and therefore `direction` and `consistency` are inverted** relative to the actual value migration. A market whose value area rose all week is reported `direction=DOWN, consistency=CONSISTENT_DOWN`. This feeds directly into `edge_detector._determine_direction` (−30 pts for "DOWN CONSISTENT", `edge_detector.py:510-513`), synthesizer scenario boosts, and the `value_migration_direction` field in the StateVector/CSV. This is the single strongest evidenced mechanism in these files for end-of-pipeline directional contradiction.

**Silent failure modes.** The ordering contract is enforced nowhere (no timestamp check); zero-POC guards return 0 change contributions (84-87, 94); `UNKNOWN` consistency passes synthesizer Gate 3.

---

## LAYER 2 (STATISTICAL)

## 6. `vanguard/layer2_statistical/state_calculator.py` (920 lines)

**Role.** Converts `VanguardInput` + `AuctionVerdict` into the `StateVector` fingerprint used for actuarial matching. Invoked between Layer 1 and `actuarial_query`. Constants: `SCHEMA_VERSION = "2.2.0"` (9-dim), `BUCKET_SCHEMA_VERSION = "1.1.0"` (lines 22-24), both written to every signal row.

**Inputs.** `vanguard_input.technical` (ohlcv, atr, bb, adx, ema21/50, 52w extremes, vwap, `wyckoff_phase_bucket`/`wyckoff_phase`, `atr_percentile_rank`, `ivp_252d`/`iv_percentile`/`iv_rank`, `crabel_compression_state`, `horizon_bucket`, intraday fields), `options.uoa`, `macro` (vix, vix_history, spy_trend, sector_relative_strength), `calendar` (earnings dates), `auction_verdict`.

**Output.** `StateVector` — full field list at lines 229-337. Key downstream-read fields and value sets:
- `vol_regime ∈ {COMPRESSION, NORMAL, EXPANSION}`; `atr_percentile`, `bb_width_percentile`, `iv_percentile`.
- `trend_direction ∈ {UP, DOWN, SIDEWAYS}`; `trend_maturity ∈ {EARLY, MIDDLE, LATE, SIDEWAYS_BUILDING, SIDEWAYS_RANGING}` (v2.2.0 replaced `N/A`).
- `structure_quality ∈ {STRONG, NEUTRAL, WEAK}`; `liquidity_condition ∈ {HIGH, NORMAL, LOW}`; `relative_volume`.
- `positioning_bias ∈ {NET_LONG, NET_SHORT, NEUTRAL}` (see defect below); `put_call_ratio`.
- `macro_regime ∈ {RISK_ON, RISK_OFF, TRANSITIONAL_BULLISH, TRANSITIONAL_BEARISH, TRANSITIONAL_NEUTRAL}`.
- `catalyst_proximity ∈ {HIGH, MEDIUM, LOW, NONE}`; `earnings_window ∈ {PRE_10D, PRE_20D, PRE_30D, FAR}`; `days_to_earnings` (−1 = none); `days_since_earnings`.
- Buckets: `adx_bucket ∈ {WEAK(<20), MODERATE(20–35), STRONG(>35)}` (789-801); `atr_pct_bucket ∈ {LOW(<33), MID(33–66), HIGH(>66)}` (804-816); `wyckoff_phase_bucket ∈ {ACCUMULATION(A/B/C), MARKUP(D/E), DISTRIBUTION, UNKNOWN}` (819-849, single-letter matched first per 2026-03-07 fix).
- V2 fields: `phase_v2 ∈ {EARLY_TRANSITION, CONTINUATION, EXHAUSTION}`; `momentum_bucket ∈ {LOW(<15), MID(15–30), HIGH(30–45), EXTREME(≥45)}` of `momentum_score = adx × atr_pct / 100` (133-145); `location_bucket ∈ {NEAR_HIGH(pfh<10%), NEAR_LOW(pfl<10%), MID_RANGE(both>30%), TRANSITION_ZONE}` (155-161); `transition_flag_v2`; `early_candidate` (MID momentum + NEAR_LOW/MID_RANGE + EARLY_TRANSITION, 168-172); `state_v2` string `vol|trend_dir|structure|phase_v2|momentum|location` (223-227); `positional_strategy=True` hard-coded (line 329 — permanently disables edge_detector Gate 0 penalty).
- 9-dim match fields: `iv_regime ∈ {LOW_IV, HIGH_IV, ELEVATED_IV, NORMAL_IV}` (177-185, a *realized-vol proxy*: COMPRESSION→LOW_IV, EXPANSION→HIGH_IV, atr≥50→ELEVATED_IV); `volume_bucket ∈ {LOW(<0.7), NORMAL(≤1.5), HIGH(≤3.0), SPIKE}`; `crabel_state ∈ {CRABEL_READY, COILING, NONE}` (199-213, discovery override else proxy: COMPRESSION+WEAK→CRABEL_READY; LOW atr bucket+WEAK/MODERATE→COILING); `horizon_bucket ∈ {SHORT, MEDIUM, LONG}` default `MEDIUM` (215-220).
- `state_hash` (see below), `confidence`, `intraday_*` fields, `schema_version`, `bucket_schema_version`.

**Core calculations.**
- `_calculate_volatility_regime` (339-394): `avg_pct = atr_pct·w_atr + bb_pct·w_bb + iv_pct·w_iv`; `< compression_percentile` → COMPRESSION, `> expansion_percentile` → EXPANSION. `atr_pct` prefers discovery `atr_percentile_rank`; `iv_pct` prefers `ivp_252d` (×100 if ≤1.0), then `iv_percentile`, then `iv_rank`, **else defaults 50.0** (line 359) — silently mid-scale.
- `_calculate_trend_maturity` (396-476): direction UP requires `ema21 > ema50 and price > ema21 and adx > uptrend_adx_min`; DOWN mirror; else SIDEWAYS. Maturity: UP+`|pct_from_high| < late_pct(default 0.07)` → LATE; `days_since_high < 30` → EARLY; else MIDDLE (mirror for DOWN). Safe-threshold fallbacks at 431-436. SIDEWAYS → `_sideways_maturity` (478-519): COMPRESSION vol or Wyckoff ACCUMULATION → `SIDEWAYS_BUILDING`, else `SIDEWAYS_RANGING`.
- `_calculate_structure_quality` (521-634): quality_score = VWAP position (above both +30 / below both +0 / mixed +15) + `acceptance.score/100×40` + control (`≠NEUTRAL`: `confidence×30`; NEUTRAL: +10). `≥ strong_quality_score` → STRONG etc. **Note the built-in long bias: being above VWAPs = "STRONG structure"**, so `structure_quality`, used as a *symmetric* match dimension, is actually a bullish-position encoding. Liquidity (569-623): the 2026-04-10 timing fix — if UTC clock in 13:30–20:00 and `current_volume < 0.50×avg`, scale partial-day volume by `390/minutes_elapsed`; classification `>1.5` HIGH / `>0.7` NORMAL / else LOW. Scaling depends on **wall-clock at run time**, so the same data can classify differently by run hour; holidays overshoot (acknowledged in comment 586-588).
- `_calculate_positioning_bias` (636-674): `skew`, `net_gex`, `net_dex`, `pc_oi_ratio` are **hard-coded 0.0/1.0** (642-646); only `pc_ratio` computed from UOA. Bias rules `pc_ratio < 0.7 and skew > 0.2` → NET_LONG, `> 1.3 and skew < −0.2` → NET_SHORT: since skew is always 0.0, **`positioning_bias` is permanently `NEUTRAL`** — a dead directional feature (also not in the hash).
- `_calculate_catalyst_proximity` (676-727): missing earnings → `{days_to:−1, window:FAR, days_since:90, proximity:NONE}`. `days_since` resolution: last_earnings_date > upstream field > proxy `91 − days_to` (694-703). Windows per 706-720.
- `_calculate_macro_regime` (729-773): `vix < 15 and spy_trend == "UP"` → RISK_ON; `vix > 25 or spy_trend == "DOWN"` → RISK_OFF; else TRANSITIONAL split: SPY UP + `vix < vix_history[-5]` → TRANSITIONAL_BULLISH; `not spy_bullish or (history and not vix_falling and vix > 20)` → TRANSITIONAL_BEARISH; else TRANSITIONAL_NEUTRAL. **Any non-"UP" spy_trend (e.g. "SIDEWAYS") in the transitional band maps to TRANSITIONAL_BEARISH** (line 765) — a bearish-leaning default.
- `_percentile` (775-784): rank in history; empty history → 50.0 (silent mid-scale).
- **`_generate_state_hash` (851-895)**: `state_hash = md5("vol_regime_trend_direction_trend_maturity_structure_quality_catalyst_proximity_adx_bucket_atr_pct_bucket_wyckoff_phase_bucket_macro_regime")[:16]`. Ticker deliberately excluded (docstring 860-864). Note comment 874-877: DB rows lacking wyckoff cause Stage-1 fallback — but the **active `actuarial_query` never uses this hash at all** (see file 7).
- `_calculate_state_confidence` (897-920): `data_quality_score × (0.8 if current volume < 0.5×avg) × (0.7 + 0.3×auction.confidence)`, capped 1.0.

**Directional logic.** `trend_direction` (feeds ±10 in `_determine_direction` and exhaustion gate), `macro_regime` (EV floors, exhaustion proximity, right_side_score), the dead `positioning_bias`. Ambiguity behavior: everything defaults toward middle values (percentiles 50, iv 50, horizon MEDIUM) — silent neutral, never insufficient-data.

---

## 7. `vanguard/layer2_statistical/actuarial_query.py` (1369 lines, ~64KB)

**Role.** Matches the StateVector against the actuarial parquet DB (v7 governed; 5.7–5.9M rows per comment at line 818) and returns `ActuarialOutcomes`. Invoked once per ticker after state calculation; output consumed by `edge_detector`, `scenario_builder`, main.py CSV (`layer2__state_match_*` columns), options layer (`win_rate_for_hold`), EIL/PSE/MVE (per comment 369-371).

**Inputs.** DB path: caller > `ACTUARIAL_DATABASE_PATH`; `__init__` (191-240) auto-upgrades an implicit legacy default to `actuarial_database_v7.parquet` with a warning, raises `FileNotFoundError` if missing, warns if filename isn't v7. Loads only `ACTUARIAL_QUERY_COLUMNS` (53-92): match dims + outcomes (`outcome_5d/10d/20d_return`, `outcome_max_drawdown_*`, `outcome_hit_5pct_up_5d`, `outcome_hit_7pct_up_10d`, `outcome_hit_10pct_up`, `outcome_hit_5pct_down_before_10up`, `outcome_days_to_10pct`, `outcome_category`) + v6 diagnostics (`future_momentum_bucket`, `transition_flag_v2`, `momentum_delta`, `atr_delta`, `adx_delta`, `early_candidate`).

**Match ladder** — `_find_similar_states` → `_find_match_ladder_states` (847-995); the legacy Stage 0/1/2 block was retired as dead code (997-1005). The `state_hash` MD5 is **not used**; matching is column equality on named dims:
- `MATCH_EXACT_DIMS` (17-32): `vol_regime, trend_direction, structure_quality, phase_v2, momentum_bucket, location_bucket, wyckoff_phase_bucket, trend_maturity, iv_regime, crabel_state`. `MATCH_RELAXED_DIMS` (33-38): `vol_regime, trend_direction, structure_quality, wyckoff_phase_bucket`.
- Value normalisation `_normalise_match_value` (500-514): **`""`, `NONE`, `N/A`, `NA`, `NAN`, `UNKNOWN` all normalise to `None`**, and `_available_match_dims` (525-526) then **drops that dimension from the match entirely**. So a ticker with `wyckoff_phase_bucket=UNKNOWN` exact-matches across *all* Wyckoff phases and is still tagged `state_match_method=EXACT, similarity=1.0`.
- EXACT (861-887): sample floor `_horizon_sample_min(None)` = **60** (5D:30, 10D:60, 20D:100 — but `preferred_horizon` is deliberately None here, line 854-857, so it's always 60). RELAXED (889-915): floor 100 (relaxed map 5D:60/10D:100/20D:150). ANALOGUE (917-966): weighted per-dim equality score with `MATCH_SIMILARITY_WEIGHTS` (39-49: vol .20, trend_dir .18, structure .15, phase_v2 .12, momentum .10, location .08, wyckoff .08, maturity .05, iv .04); keep rows with score ≥ `ANALOGUE_MIN_SIMILARITY = 0.70`; need ≥ `ANALOGUE_MIN_SAMPLES = 100`. Else UNKNOWN (968-995): empty frame, `signal_type=NO_EDGE`, `fallback_reason` chain string.
- Every path is tagged via `_tag_match` (448-483) with `state_match_method/stage/dimensions/quality/is_exact/sample_size` + `signal_type`, `momentum_tier`, confidence attrs, `matched_state_key`, `original_state_key`, `fallback_reason`.
- Sample-quality labels `_sample_quality` (542-550): ≥300 HIGH_SAMPLE, ≥100 MODERATE_SAMPLE, ≥30 LOW_SAMPLE, else INSUFFICIENT_SAMPLE. Confidence buckets `SAMPLE_CONFIDENCE_THRESHOLDS` (114-119) per horizon group; `CONFIDENCE_WEIGHTS` (121-138): EXACT HIGH 1.00 … UNKNOWN 0.30; RELAXED HIGH 0.85 … ; ANALOGUE weight by similarity (586-595: ≥0.85+good bucket→0.70, ≥0.80→0.60, ≥0.70→0.50, else 0.35).

**`query()` (298-446).**
- `df is None/empty` → `_empty_outcomes()` (141-180): all-zero probabilities/EV, `insufficient_data_reason="No actuarial data available"`, `confidence_level=0.0` — explicit fail-closed; audit fields default UNKNOWN.
- `< 10` matched rows → empty outcomes *plus* calibration dict (316-325).
- `_calculate_outcomes` (1089-1231), on `sample_20d = dropna(outcome_20d_return)`:
  - `prob_up_10pct = mean(outcome_hit_10pct_up)` (1100); `prob_down_5pct = mean(outcome_hit_5pct_down_before_10up)` (1101); `prob_trend_cont = mean(outcome_20d_return > 0)` (1102).
  - `win_rate_20d = P(return>0)` (1113) — **directional win rate, not target-hit rate** (comment 1113, 1119).
  - `ev_20d = win_rate·median_gain(winners) + (1−win_rate)·median_loss(losers)` (1119); loser/winner medians default **+0.05/−0.03 when a side is empty** (1107-1108 — fabricated values on one-sided samples).
  - `sharpe = mean/std` (1114); `kelly = (prob_up_10pct·avg_win − (1−prob_up_10pct)·avg_loss)/avg_win`, clamped [0, 0.25] (1125-1126) — note Kelly mixes *target-hit* probability with *directional* win/loss magnitudes.
  - `recommended_hold = median(outcome_days_to_10pct)` if `prob_up_10pct > 0.5` else 20 (1128); `confidence_level = min(1, n/50)` (1130) — **saturates at 50 rows**, so edge_detector Gate 2 (min_data_confidence) passes for essentially any match ≥ the ladder floors.
  - 5d/10d blocks (1132-1178) mirror the 20d formulas; return-percentile grids p01–p99 per horizon via `_return_percentiles` (1058-1087; None not 0.0 when absent).
  - v6 stats: `_future_bucket_stats` (1007-1036) — modal `future_momentum_bucket`, distribution, confidence = modal share, sample size; `_transition_delta_stats` (1038-1056) — means of `transition_flag_v2`, `momentum_delta`, `atr_delta`, `adx_delta`, `early_candidate`.
- **`_adjust_for_intraday_context` (1233-1369)** — the "hybrid" intraday overlay:
  - Fail-closed **only** when `intraday_rows == 0` exactly (1247-1249); `None` (attr absent) proceeds.
  - Multipliers: AT_SUPPORT ×1.6 (or ×1.3 in uptrend); AT_RESISTANCE ×1.2 in uptrend else ×0.7; NEAR_SUPPORT ×1.2; ACCUMULATION ×1.3 / DISTRIBUTION ×0.75; BUYERS_STRENGTHENING ×1.2 / SELLERS_STRENGTHENING ×0.8; clamped [0.4, 2.5] (1262-1297).
  - `adj_prob_up = min(0.95, prob_up_10pct × factor)` (1299); prob_down deflated/inflated by factor (1301-1304).
  - **Triple-barrier EV redefinition (1306-1318)**: `adj_ev_20d = prob_target·(median_gain×factor) + prob_stop·median_loss` — this replaces the win-rate-based EV with a **target-hit-probability EV, and this recalculation runs even when `adjustment_factor == 1.0`** (line 1318 is unconditional once the function is entered). The function's own FIX 1 docstring (1238-1244) states this substitution "inflat[es] reported EV by ~50x". So: whenever any intraday rows exist, `expected_value_20d` handed downstream is on a different (much larger) scale than the base actuarial EV. `win_rate` is preserved un-adjusted (1347), and shorter-horizon EVs/win-rates are multiplied by the same scalar (1321-1325). The v6/percentile fields are copied back from base (424-444) because the adjusted constructor drops them.
- Calibration `_probability_calibration` (683-724): shrink toward population baseline — `adjusted_prob = baseline + weight·(raw − baseline)` with `weight = confidence_weight`; `probability_edge = adjusted − baseline`; `probability_verdict` (616-626): edge ≥0.10 STRONG_EDGE, ≥0.05 MODEST_EDGE, >0 WEAK_EDGE, ==0 NO_STAT_EDGE, <0 NEGATIVE_EDGE. Emits `raw_prob_up/down_{5,10,20}d`, `raw_prob_target_hit`, `raw_prob_stop_hit`, `raw_expected_return/drawdown/time_to_target`, `baseline_probability`, `adjusted_prob_target_hit`, `adjusted_expected_return`.
- `signal_type` `_signal_type_from_values` (743-756): from **state values only** — `CONTINUATION` (phase CONTINUATION + momentum HIGH/EXTREME + location ≠ NEAR_HIGH), `TRANSITION` (EARLY_TRANSITION + LOW/MID momentum + TRANSITION_ZONE/NEAR_LOW), else `STRUCTURAL_MATCH`; `NO_EDGE` only on UNKNOWN match.
- `momentum_tier` (774-809): CONTINUATION — modal future bucket EXTREME→TIER_1_EXPLOSIVE, HIGH→TIER_2_SUSTAINING, MID→TIER_3_BUILDING, else TIER_4_FLAT; TRANSITION — future HIGH/EXTREME with current LOW/MID→TIER_1_ACCELERATING, MID→TIER_2_BUILDING, positive median adx_delta→TIER_2_BUILDING, else TIER_4_FLAT; STRUCTURAL_MATCH→"N/A".
- `forward_momentum_confidence` (394-411): fraction of matched rows whose `future_momentum_bucket` rank > current rank (fallback: `momentum_delta > 0` share).
- `preferred_horizon` (731-741): argmax over (EV, win_rate) tuples of the three horizons — **selected *after* the intraday adjustment**, i.e. on the inflated EVs.

**Directional logic.** Every probability/EV in this file is defined on **long-side outcomes** (`outcome_hit_10pct_up`, `> 0` returns). There is no down-target symmetric set; a bearish thesis is served the same long-framed EV. Ambiguity: UNKNOWN match → explicit zeros + reason; missing dims → silent dimension-dropping (see EXACT overstatement above).

**Silent failure modes.** Broad `except` on `_find_similar_states`/`_calculate_outcomes`/`_adjust...` printing warnings and continuing (309-341); default winner/loser medians +5%/−3% (1107-1108); confidence saturation at n=50 (1130); dimension-dropping on UNKNOWN; the unconditional triple-barrier EV redefinition; `category` cast failures swallowed (267-271).

---

## 8. `vanguard/layer2_statistical/edge_detector.py` (741 lines)

**Role.** Multi-gate verdict engine producing `EdgeAssessment` from (StateVector, ActuarialOutcomes, AuctionVerdict). Consumed by main.py (TRADE / SETUP_FORMING / NO_EDGE routing), EIL, position sizing.

**Outputs (`EdgeAssessment`).** `has_edge: bool`, `edge_direction ∈ {CALL, PUT, NONE}`, `edge_magnitude` (= net_ev), `confidence`, `right_side_score`, `failed_gate ∈ {AUCTION_CONFLICTED, DATA_CONFIDENCE, TREND_EXHAUSTED, OPTIONS_VIABILITY, REGIME_MINIMUM_EV, SETUP_FORMING}`, `no_edge_reason`, `rationale`, `signal_type`, `forward_momentum_confidence`, `bucket_edge_quality ∈ {EARLY_EXPANSION_STRONG, BUCKET_STRONG, EARLY_CANDIDATE_MODERATE, STATISTICAL_STRONG, STATISTICAL_MODERATE, LEGACY_MODERATE, WEAK}`.

**Constants.**
- `REGIME_EV_FLOORS` (89-96): RISK_ON/TRANS_BULLISH (0.0005, 0.36); TRANS_NEUTRAL/TRANSITIONAL (0.0010, 0.38); TRANS_BEARISH (0.0015, 0.40); RISK_OFF (0.0020, 0.43) — recalibrated twice (FIX RC-2 2026-04-16; FIX-EV1 2026-05-02 comments 68-88: prior floors caused 43/44 then 100% has_edge=False).
- `REGIME_SETUP_FORMING_FLOORS` (98-105): (0.0000, 0.32) … RISK_OFF (0.0008, 0.38).
- `CONTINUATION_FASTPATH_EV_FLOOR = 0.0015`; `TRANSITION_SETUP_EV_FLOOR = 0.0020`; `TRANSITION_ACCELERATION_EV_FLOOR = 0.0030` (107-109).
- `_scaled_ev_floor` (112-121): `floor × (0.65 + 0.35·min(1, n/500))`.
- `EXHAUSTION_PROXIMITY` (125-132): RISK_ON −0.04 … RISK_OFF −0.10; `EXHAUSTION_MIN_ADX = 22`; `EARNINGS_BLACKOUT_DAYS = 10`, `EARNINGS_REENTRY_DAYS = 3`, `IV_SPIKE_PERCENTILE = 85`.
- `calculate_trading_costs` (48-62): HIGH 0.15%, NORMAL 0.40%, LOW 0.80% round-trip — **computed but no longer subtracted** (see Gate 5).

**Gates (detect_edge, 168-402).**
- Gate 0 (175-205): intraday penalty only when `intraday_rows==0 and not positional_strategy`; state_calculator hard-codes `positional_strategy=True` (line 329 there), so this gate is **permanently inert** — `effective_auction_state = auction_verdict.auction_state` always.
- Gate 1 (207-212): `auction_state == "CONFLICTED"` → NO_EDGE.
- Gate 2 (214-223): `outcomes.confidence_level < min_data_confidence` → NO_EDGE. Because confidence saturates at n=50 (file 7) this rarely fires post-match; only UNKNOWN-match zeros trip it.
- Gate 3 `_check_trend_exhaustion` (408-446): veto only when `trend_maturity == "LATE"` and `adx ≥ 22` and (UP: `distance_from_52w_high ≥ proximity_threshold` — i.e. within 4–10% of high depending on regime; DOWN mirror vs 52w low).
- Gate 4 `_check_options_viability` (452-497): earnings within (0, 10] days veto; earnings (0, 3] days ago veto; `iv_percentile ≥ 85 and vol_regime ≠ COMPRESSION` veto. Liquidity veto removed (FIX-EV3, comment 459-464).
- Gate 5 (241-402): **the EVEngineV2 call is dead weight** — `ev_res = _EV_ENGINE_V2.evaluate(ev_in)` (285) is computed then discarded; all three branches set `net_ev = outcomes.expected_value_20d` with no cost subtraction (288, 290, 292; FIX-EV2 rationale 249-255). `win_rate = outcomes.win_rate` (P(return>0)).
  - **Signal-aware fastpaths** (304-353): `signal_type == "CONTINUATION"` and `expected_value_10d > 0.0015` → immediate `TRADE` (bypasses regime floors and win-rate floor entirely); `TRANSITION` + `momentum_tier == TIER_1_ACCELERATING` + `EV20d > 0.0030` → `TRADE`; `TRANSITION` + `EV20d > 0.0020` → `SETUP_FORMING` probe.
  - Standard: `net_ev ≥ scaled ev_floor and win_rate ≥ wr_floor` → TRADE (360-370); else setup-forming floors (372-389); else NO_EDGE with reason(s) (391-402).

**DIRECTIONAL LOGIC — `_determine_direction` (503-534), the pipeline's CALL/PUT decision:**
- `controller == BUYERS`: `+40 × control.confidence`; SELLERS: `−40 × confidence`.
- `migration.direction == "UP"`: +30 if consistency startswith "CONSISTENT" else +15; "DOWN": −30/−15 (510-513). **Feeds on the inverted migration sign from file 5.**
- `prob_up_10pct_20d > 0.55` → +20; `< 0.35` → −20 (515-518). Note this probability is *post intraday multiplication* (capped 0.95), so a ×1.6 support adjustment can push a 0.40 base to 0.64 → +20 bullish.
- `trend_direction == UP and prob_trend_continues_20d > 0.60` → +10; DOWN mirror −10.
- `score > 15` → CALL; `< −15` → PUT; **else tie-break: controller BUYERS→CALL, SELLERS→PUT, otherwise `return "CALL"` (line 534) — ambiguity resolves silently bullish.**
- There is no consistency check between `edge_direction` and the EV that passed Gate 5: `net_ev` is the **long-framed** actuarial EV, so a PUT verdict is justified by a long-side expected value.

`_calculate_confidence` (536-549): `state.confidence×0.25 + outcomes.confidence_level×0.35 + auction.confidence×0.40` (intraday 0.60 haircut inert as above). `_calculate_right_side_score` (551-589): base 50 + auction_state (ALIGNED +25 / TRANSITIONING +15 / SEARCHING +5) + `20×control.confidence` + migration consistency (+15 CONSISTENT / +10 TRENDING) + prob_up extremity (+10 if >0.60 or <0.30; +6 if >0.55 or <0.35) + trend/continuation +5 + regime bonus (RISK_ON & prob_up>0.50 +15; RISK_OFF & prob_up<0.40 +15; TRANSITIONAL & >0.45 +8 — **the sub-classified regimes `TRANSITIONAL_BULLISH/BEARISH/NEUTRAL` match none of these three string tests, so they get no regime bonus**, lines 577-582) + earnings drift +5 (uses `prob_drift_into_earnings`, a field never set in these files → always skipped).

`_bucket_edge_quality` (655-694): thresholds quoted in docstring — EARLY_EXPANSION_STRONG (early + n≥100 + conf≥0.55 + future HIGH/EXTREME); BUCKET_STRONG (n≥100, conf≥0.60, future HIGH/EXTREME); EARLY_CANDIDATE_MODERATE (early + n≥50 + conf≥0.50 + future MID); STATISTICAL_STRONG/MODERATE (high_sample = size≥100 and match_quality ∈ {HIGH, HIGH_SAMPLE, MEDIUM_HIGH}, prob_edge ≥ 0.10 / 0.05); LEGACY_MODERATE (EV20d ≥ 0.015); WEAK.

**Silent failure modes.** Dead EVEngineV2 call with bare `except` (289); rationale text still prints "Trading Costs −x%" and "Net EV" although nothing is subtracted (603-605) — the human-readable audit contradicts the computation; `_setup_forming` emits `has_edge=False` **with a populated `edge_direction`** (732-741), so downstream consumers reading direction without checking `has_edge` see a directional signal on a non-edge; CONTINUATION fastpath ignores auction alignment and win rate entirely.

---

## 9. `vanguard/layer2_statistical/scenario_builder.py` (535 lines)

**Role.** Header says "Layer 3" — builds three `TradeScenario`s (aggressive/moderate/conservative) for a ticker that already has a direction. Invoked by main pipeline with `direction` from `EdgeAssessment.edge_direction`. Outputs consumed by the advisory report / options layer.

**Top-level items.**
- `compute_scenario_probabilities(row)` (43-70): from `composite` (0-100, default 50) alone — `prob_breakout = min(0.65, 0.25 + composite/200)`, `prob_rejection = max(0.10, 0.45 − composite/250)`, `prob_drift = max(0.05, remainder)`, normalised to 1.0. Purely score-shaped, no historical input.
- `MultiScenarioBuilder.build/compute_probs` — wrappers; `build_scenarios` (105-130) returns the three scenarios.
- `_hold_days` (132-138): `recommended_hold_days` (default 20) × factor. `_horizon_metrics` (140-154): `outcomes.win_rate_for_hold(hold_days)` etc. with fallback to 20d fields on any exception (bare `except` ×3 — silent horizon degradation).

**Per scenario (aggressive 156-268 / moderate 270-388 / conservative 390-499), all share the pattern:**
- Entry: aggressive = now (±0.5%); moderate = trigger price (POC reclaim if below POC, else VA-low entry if BELOW_VALUE, else `price×1.02` hold-above); conservative = `VAH×1.02` breakout (VAH fallback `price×1.05`).
- Stops **are** direction-aware: CALL → below VA-low/POC (`min(VAL×0.99, POC×0.985)` aggressive; `POC×0.97` moderate; `VAH×0.98` conservative); PUT → above (`VAH×1.01/1.03`, `VAL×1.02`).
- **Targets are NOT direction-aware**: `target_1 = entry × (1 + horizon_gain)` etc. (lines 186-187, 310-311, 425-426) — for `direction == "PUT"` the targets sit *above* entry while the stop sits above entry too; PUT scenarios are geometrically incoherent.
- Win probability: `max(scenario_base_probability, horizon_win_rate)` then additive boosts (aggressive: +0.05 acceptance≥50, +0.05 control conf>0.60, +0.03 migration≠SIDEWAYS; moderate: +0.03/+0.03; conservative: +0.02), capped at `max_probability` (189-197, 313-319, 428-432). The `max(base, …)` floor **fabricates a minimum probability regardless of actuarial win rate**.
- EV = `p·gain + (1−p)·loss` with scenario haircuts (moderate gain ×0.9; conservative gain ×0.7, loss ×0.6); Kelly `p − (1−p)/RR` clamped [0, 0.25] (conservative additionally ×0.5); sizes = Kelly × config factors capped by `max_position_size`.
- `drawdown_probability = prob_down_5pct_before_up_10pct` × (1.0 / 0.7 / 0.5).
- `right_side_score` fixed bases 50/65/75 + small boosts — unrelated to edge_detector's right_side_score of the same name.
- `_design_options_strategy` (501-535): `dte = hold_days + 5`; if catalyst HIGH and `days_to_earnings > 0`, `dte = min(dte, days_to_earnings − 2)` (can go ≤0 when earnings ≤2 days away — no floor). Strike: COMPRESSION → `entry×1.03` OTM (aggressive) / `entry×1.01`; else ATM. **Strike offsets are call-shaped: for a PUT, `entry×1.03` is in-the-money, contradicting the "OTM" label** (519-527).

**Directional logic.** Consumes direction; does not set it. Migration boost uses `state.value_migration_direction != "SIDEWAYS"` — the inverted migration direction still counts as a boost (direction-agnostic here, so the inversion only affects whether the boost fires on UNKNOWN: "UNKNOWN" ≠ "SIDEWAYS" → **boost fires on missing migration data**, lines 194, 316).

---

## EV ENGINE V3 (SHADOW / PRODUCTION EVIDENCE)

## 10. `vanguard/ev_engine_v3.py` (815 lines)

**Role.** Stage EV-2B: contract-level EV for long CALL/PUT singles and bull-call/bear-put debit verticals, using the Stage EV-0 barrier sidecar. All outputs `ev3_*`; `ev3_capital_eligible` always `False` (lines 519, 63, 72 — non-capital-authoritative by construction); `ev3_status ∈ {EVALUATED_PRODUCTION_EVIDENCE, REJECTED, NOT_APPLICABLE}`.

**`EV3Policy` (27-46).** `risk_free 0.045`, `iv_stress_fraction 0.15` (stress = IV −15%), `slippage 2% of mid each side`, `one_sided_z 1.645`, `model_uncertainty_return 0.02`, `default_input_uncertainty_return 0.01`, `capital_hurdle_return 0.02`, `max_contracts_per_thesis 12`, `selection_tie_tolerance 0.005`, `minimum_open_interest 50`, `minimum_volume 1`, `maximum_spread_fraction_mid 0.35`, CRR steps 40–365.

**`EV3BarrierCache` (79-254).**
- Constructor validates required columns, duplicate keys, and that `p_target_first + p_stop_first + p_timeout == 1` to 1e-9 (93-109).
- `lookup(state_key, direction, horizon, target_distance, stop_distance)` (114-232):
  - Horizon must be exactly 5, 10, or 20 (125) → else `REJECT_BARRIER_HORIZON_UNAVAILABLE`.
  - Exact state match on the 7-dim pipe key; if absent, **fallback**: keys must be 7 parts (138), candidates must be "core aligned" (`parts[0]` vol_regime and `parts[1]` trend_direction equal, 148-152), scored by number of matching dims; best group used only if `≥ 5 of 7` match (162-164). Fallback cell = `n_effective`-weighted average of the matching states' probabilities/exit sessions, re-normalised (191-217), with floor `FALLBACK_MIN_EFFECTIVE_OBSERVATIONS = 30` (else `REJECT_BARRIER_STATE_SPARSE`) and `state_fallback_penalty_return = 0.02` added to uncertainty (229). Tagged `state_match_type = FALLBACK_k_OF_7`, `state_similarity = k/7`.
  - Grid discretisation is conservative (175-181): target snapped **up** (no easier than requested), stop snapped **down** (no wider than requested); off-grid → `REJECT_BARRIER_GRID_UNAVAILABLE`.
  - `_normalise_exit_sessions` (234-254): NaN exit-session means default to conservative values (target exits at horizon end, stop at session 1, timeout at horizon), clamped [1, horizon], with `exit_session_default_penalty_return = 0.01` added when any default used.
- **All lookup failures are explicit typed rejections — no fabricated neutral.**

**Pricing.** `american_option_price` (256-291): CRR binomial with early exercise; degenerate inputs return intrinsic. `_anchored_option_mid` (294-324): market-anchored revaluation — `exit_mid = max(mid + model(exit) − model(now), 0)`, floored at intrinsic, capped at no-arbitrage bound (spot for calls / strike for puts); elapsed calendar = `ceil(sessions×7/5)`. `_exit_return` (327-352): `exit_credit = anchored_mid × (1 − spread/2 − slippage)`, `entry_debit = ask + mid×slippage`; return = `(credit − debit)/debit` — **denominator is the per-share entry debit**.

**`evaluate_contract` (583-752), single-leg path.**
- Direction `STRANGLE/STRADDLE/NON_DIRECTIONAL` → `NOT_APPLICABLE` (602-606). Verticals dispatched (607-612). Stage-0 validation; `spread_fraction_mid > 0.35` → `REJECT_LIQUIDITY_SPREAD`.
- Barrier lookup; three exits: target at `target_spot` / stop at `invalidation_spot` / timeout at `entry_spot` (644-648), each priced base and stress (IV×0.85).
- `ev_base = Σ p_i·return_i`; `ev_stress` likewise; `ev_conservative = min(ev_base, ev_stress)` (664-666).
- Uncertainty stack (668-681): `probability_uncertainty = 1.645·sqrt(Var_p(outcomes − ev_cons)/n_effective)`; `liquidity = min(spread×0.10, 0.10)`; `quote = min(age/limit × 0.01, 0.01)`; `default_input = 0.01` if rate or dividend defaulted; + state fallback 0.02 + exit-session default 0.01. `lower_bound = ev_conservative − uncertainty_total`.
- `ev3_absolute_state` (683-688): `NEGATIVE_EV` if `ev_conservative ≤ 0`; `INDETERMINATE` if `lower_bound ≤ 0.02` hurdle; else `POSITIVE_UNVALIDATED`. Never "positive validated" — the health taxonomy is deliberately conservative.
- Output fields (691-752): full `ev3_*` audit set including `ev3_p_target/stop/timeout`, `ev3_n_effective`, six scenario returns, `ev3_ev_base/stress/conservative_return`, all uncertainty components, `ev3_ev_lower_bound_return`, match-type/similarity/source keys, defaulted flags, entry debit, `ev3_exit_mid_*`.

**`evaluate_vertical_debit` (374-580).** Both legs Stage-0-validated (`REJECT_VERTICAL_{LONG,SHORT}_LEG`); structure/expiry/multiplier/geometry checks (`long < short` strikes for CALL debit, reversed for PUT, 415-422); `entry_debit = long_ask+slip − max(short_bid−slip, 0)` must lie in `(0, width)` (429-434); exit credit clamped `[0, width]` (477); same EV/uncertainty/absolute-state math (483-509); records `ev3_max_loss/profit_per_contract`, `ev3_short_assignment_risk_modelled: False` plus limitation string (566-567).

**`select_contract` (755-811).** Evaluates ≤12 candidates; if none valid: NOT_APPLICABLE if all were, else `REJECT_NO_EVALUABLE_CONTRACT` with per-reason child counts. Ranking: **max `ev3_ev_lower_bound_return`**; ties within 0.005 broken by (quote age, liquidity uncertainty, symbol); records `ev3_selection_reason ∈ {MAX_LOWER_BOUND, LOWER_BOUND_TIE_FRESHER_TIGHTER, NOT_APPLICABLE_TO_ALL_CANDIDATES}`, `ev3_argmax_margin`, `ev3_runner_up_lower_bound_return`, candidate counts.

**Directional logic.** EV3 never *originates* direction — it consumes the upstream `canonical_direction` and prices barriers accordingly. Notably, `ev3_shadow_only` is set **False** with `ev3_evidence_mode = "PRODUCTION_EVIDENCE"` (57-58, 699-700) despite the file being "the EV3 shadow": the shadow-ness is carried only by `ev3_capital_eligible=False`.

---

## 11. `vanguard/ev3_stage0.py` (1040 lines)

**Role.** Stage EV-0: input validation contract (`validate_ev3_input`) and the barrier-sidecar builder (`accumulate_ticker_barriers` → `finalise_barrier_cache`). Non-authoritative by design (docstring 3-6).

**State key.** `STATE_DIMENSIONS` (26-34): `vol_regime | trend_direction | structure_quality | adx_bucket | wyckoff_phase_bucket | trend_maturity | atr_pct_bucket` — `build_state_key` (606-612) pipe-joins these (nulls raise). **This 7-dim key ≠ the 9-dim `state_hash`, ≠ the 10-dim actuarial match key, ≠ `state_v2`.** Also note `FIELD_ALIASES["state_key"]` (102-107) resolves in order `ev3_barrier_state_key → state_key → layer2__matched_state_key → layer2__outcomes__matched_state_key`; the layer2 matched key format is `"dim=value|…"` with 10 `dim=value` parts (`actuarial_query.py:529-530`), which fails the 7-part check in `EV3BarrierCache.lookup` (line 138-141) → if the dedicated `ev3_barrier_state_key` is ever missing, the alias chain silently supplies an incompatible key and every lookup rejects with `REJECT_BARRIER_STATE_UNAVAILABLE`.

**Grids.** Targets (36-38): 1–50% (12 points); stops (39-41): 1–25% (9 points); horizons (5, 10, 20); `shrinkage_k = 30`.

**Direction resolution.** `_normalise_direction` (169-172): LONG_CALL/BULLISH→CALL, LONG_PUT/BEARISH→PUT. `ACCEPTED_DIRECTION_STATES` (44-53) includes **`CONFLICT_STRUCTURE_LEADS`** — a direction produced *out of* a structure-vs-probability conflict is normalised to `RESOLVED` (175-189) and accepted into EV3; `REJECTED_DIRECTION_STATES` (54-62): empty/NOT_EVALUATED/PENDING/UNRESOLVED/CONFLICT/CONFLICTED/BLOCKED → `REJECT_DIRECTION_UNRESOLVED`.

**`validate_ev3_input` (244-563)** — explicit typed rejects, no fabrication:
- Ticker, direction (CALL/PUT only; non-directional → NOT_APPLICABLE), resolution status.
- Thesis prices > 0 (`REJECT_THESIS_PRICE`); topology `invalidation < entry < target` for CALL (reversed for PUT, 320-333, `REJECT_THESIS_TOPOLOGY`); `rr = target_dist/stop_dist > 0` (`REJECT_RR_ZERO`).
- Horizon `∈ {1_5D, 6_10D, 11_20D}` and `planned_hold_sessions` must equal the endpoint (5/10/20; 358-370, `REJECT_HORIZON`) — intermediate holds rejected up front by design.
- `expected_move_*d`, when present, must be a fraction in (0, 0.60) (`REJECT_UNIT_MOVE`).
- Contract: state_key/symbol/structure (`LONG_SINGLE` only here), strike > 0, valid expiration, **timezone-aware quote timestamp required** (`REJECT_QUOTE_TIMESTAMP`); freshness: EOD 24h, intraday 15min default (440-441); `REJECT_QUOTE_STALE`.
- Quote: `0 ≤ bid ≤ ask`, ask > 0 (`REJECT_QUOTE_INVALID_MARKET`); `bid == 0` → `REJECT_LIQUIDITY_ZERO_BID`; `spread_fraction_mid ∈ [0, 2)` (`REJECT_UNIT_SPREAD` — economic tradeability deliberately deferred to policy, 481-484).
- DTE integer 1–180 and `dte ≥ ceil(hold×7/5) + 3` buffer (`REJECT_DTE`, `REJECT_DTE_FEASIBILITY`, 493-506).
- Greeks: delta sign must match direction, |delta| ∈ (0,1) (`REJECT_UNIT_DELTA`); gamma ≥ 0; theta present and `|theta| ≤ 0.20×mid` per day (`REJECT_UNIT_THETA`); vega ≥ 0; IV ∈ (0, 5]; OI ≥ 50 / volume ≥ 1 (`REJECT_LIQUIDITY`); multiplier > 0; rate ∈ [−0.05, 0.25], dividend ∈ [0, 0.25] when given.
- `EV3ValidationResult.diagnostic_row` records reason + field provenance JSON for every row.

**Barrier build.**
- `classify_barrier_path` (615-655): per forward OHLC path, first bar whose high/low crosses the target/stop level; same-bar double touch → `AMBIGUOUS`; neither → `TIMEOUT`.
- `accumulate_ticker_barriers` (693-834): vectorised — forward high/low matrices per signal date (`_forward_matrix`, right edge NaN-padded); first-hit days per grid point per direction; maturity filtering per horizon (`used_rows_by_horizon`, `immature_rows_by_horizon` returned as coverage, 736-742, 829-834); per-state calendar block sets (5d→7-day blocks, 10d→14, 20d→28, line 781) for effective-n.
- `finalise_barrier_cache` (837-951): `n_effective = min(n_nominal, unique calendar blocks)` (866) — overlap-deduplicated sample size; `shrinkage_weight = n_eff/(n_eff+30)` (867); **ambiguous outcomes allocated to the stop leg** ("ALLOCATE_TO_STOP_FOR_PROBABILITY", 884, 930) — conservative; probabilities shrunk toward the **pooled cross-state prior** for that (direction, horizon, target, stop) cell (885-892) and renormalised; count invariant `total == n_nominal` enforced (876-879); probability-sum invariant ≤1e-9 (948-950); duplicate keys raise.
- `barrier_cache_audit` (1000-1032): PASS/FAIL on probability sum + duplicates, plus rows/states/directions/horizons/ambiguous counts — this is the coverage/health record.
- `sha256_file` (1035-1040): artifact hashing.

**Silent failure modes.** Essentially none — this is the most fail-closed file in the set. The one soft spot: shrinkage toward the pooled prior means a thin state's `p_target_first` is mostly the **cross-state average** (at n_eff=30, weight is 0.5), which is by design but means low-sample state probabilities are only half state-specific.

---

## Observations relevant to "contradicting signals / edge lost by end of run" (evidence-only)

1. **Value-migration sign inversion (highest confidence).** `auction_synthesizer.py:61-67` builds the session profile list oldest-first; `value_migration.py:34` requires most-recent-first and computes `poc_series[0] − poc_series[-1]` (line 84) and `daily_changes[i] = poc[i] − poc[i+1]` (93-96). Result: `migration.direction` and `consistency` are inverted, then consumed at ±30/±15 points in `edge_detector._determine_direction` (510-513), in the synthesizer verdict Gate 3 and scenario boost (198), and in the `value_migration_direction` CSV field. A consistently rising value area actively pushes the direction score toward PUT.

2. **EV is redefined and inflated whenever intraday rows exist.** `actuarial_query._adjust_for_intraday_context` recomputes `expected_value_20d` as `prob_target·gain + prob_stop·loss` using the *target-hit* probability (line 1318, unconditional inside the function), which its own FIX 1 docstring (1238-1244) says inflates EV ~50×. Gate 5 floors (0.05–0.20%) were calibrated on the *base* actuarial EV space (`edge_detector.py:76-96`). So EOD runs with intraday data and Morning Gate runs without it evaluate against the same floors with EVs on different scales — a direct mechanism for evening TRADE / morning NO_EDGE flips.

3. **Direction and EV are decoupled.** `net_ev` for Gate 5 is always the long-framed 20d actuarial EV (`edge_detector.py:288-292`; all DB outcome columns are up-target based, `actuarial_query.py:73-84`), while `edge_direction` is decided separately by auction control/migration (503-534). A PUT verdict is therefore certified by long-side EV, and the tie-break at line 534 defaults ambiguous scores to CALL.

4. **Four incompatible state identities.** `state_hash` (9-dim MD5, `state_calculator.py:851-895`) is written to every row but **never used for matching**; the live actuarial match uses 10 named dims (`actuarial_query.py:17-32`); `state_v2` is 6 dims (223-227); EV3 uses a 7-dim pipe key (`ev3_stage0.py:26-34`). The required downstream `behaviour_state_hash` (`execution_intelligence_runner.py:2713`) is produced by none of these files. Two engines can classify the same ticker into different historical cohorts by construction.

5. **UNKNOWN dims silently widen the "EXACT" match.** `_normalise_match_value` maps UNKNOWN/N-A to None and `_available_match_dims` drops the dim (`actuarial_query.py:500-526`), so e.g. `wyckoff_phase_bucket=UNKNOWN` yields an `EXACT`/similarity-1.0 label on a broader cohort. Combined with `confidence_level = min(1, n/50)` (1130), Gate 2 passes on almost any match, and confidence-weight nuance (`confidence_weight`, `state_match_quality`) is not consulted by any gate in `edge_detector`.

6. **Insufficient data flows through as positive.** Acceptance `INSUFFICIENT_DATA` passes synthesizer Gate 1 as a *favorable* factor (`auction_synthesizer.py:346-351`) and can make `auction_state=ALIGNED` with negative confidence (line 373); UNKNOWN partial credits fabricate mid-grade acceptance scores (`value_acceptance.py:405-428`); migration `UNKNOWN` passes Gate 3 (362-365) and still triggers the scenario probability boost in `scenario_builder` (194, 316: `!= "SIDEWAYS"`).

7. **Fastpaths bypass the alignment logic.** `signal_type=="CONTINUATION"` with `EV10d > 0.15%` goes straight to TRADE with no win-rate, regime-floor, or auction check (`edge_detector.py:307-319`); `signal_type` itself is computed from state buckets only, not outcomes (`actuarial_query.py:743-756`). Tickers can thus be TRADE-graded on a 0.15% underlying EV while similar tickers fail regime floors at 0.10–0.20%.

8. **Scenario/strike geometry contradicts PUT directions.** Targets always above entry (`scenario_builder.py:186-187, 310-311, 425-426`) and COMPRESSION strikes always `entry×1.01/1.03` labeled OTM (519-527) regardless of direction; all synthesizer scenarios are long-triggered (251-307). A PUT verdict arrives at the report with bullish triggers/targets — visible self-contradiction in the final output.

9. **Reporting contradicts computation.** Rationale prints "Trading Costs −x%" and "Net EV" (`edge_detector.py:603-605`) while no cost is subtracted (288-292); EVEngineV2 is invoked and discarded (285-288); regime bonus in right_side_score cannot fire for the new TRANSITIONAL_BULLISH/BEARISH/NEUTRAL labels (577-582) introduced in `state_calculator.py:754-768` — the regime split raised EV floors for BEARISH but silently removed the scoring bonus for all transitional states.

10. **Run-time-dependent state.** Liquidity classification scales partial-day volume by wall clock (`state_calculator.py:590-616`), and `macro_regime` maps any non-UP transitional SPY trend to TRANSITIONAL_BEARISH (765) — so evening vs morning runs can produce different `volume_bucket`/`liquidity_condition`/regime floors for identical price history, changing both the matched cohort (`volume_bucket` is a 9-dim enrichment dim) and Gate 5 thresholds between the EOD run and the Morning Gate.

11. **EV3 is the outlier in rigor — and will disagree with Layer 2 by design.** EV3 prices contract-level, cost-, stress- and uncertainty-adjusted EV with a 2% capital hurdle and conservative ambiguity allocation (`ev_engine_v3.py:664-688`, `ev3_stage0.py:884`), while Gate 5 passes gross underlying EV ≥ 0.05–0.20%. Most Layer-2 TRADE signals will legitimately read `NEGATIVE_EV`/`INDETERMINATE` in EV3 evidence; also `ev3_shadow_only=False` despite the shadow designation (57, 699), and the state-key alias chain (`ev3_stage0.py:102-107`) can silently feed an incompatible 10-dim `layer2__matched_state_key` into the 7-dim barrier lookup, mass-rejecting with `REJECT_BARRIER_STATE_UNAVAILABLE`.