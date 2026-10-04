# AVSHUNTER — Vanguard stage path audit (direction / side-correctness evidence base)

Read-only static audit of `/mnt/user-data/uploads/AVSHUNTER-Intelligence/`, 30 Sep 2026. No pipeline code was run against data, and no file was modified. `python3.13 ast` was used only to list dataclass fields and constant lists.
Line numbers refer to the staged copy.

**Staged-source gaps (limits on verification):** these are imported on the path but are not in the upload. `avshunter/c0_run/canonical_manifest.py`; most of `canonical_data/*` (registry, historical_prices, session_clock, lifecycle, feature_flags); `contracts/enrichment_ledger`'s callers are present but not `canonical_data.session_clock`. The `C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py` (the `lookup_state`/`load_cache` used by the enrichment pass) is missing. The scripts that add the v6-compatibility columns to the production parquet are missing (`build_state_v2.py`, `add_early_candidate.py`, `enrich_actuarial_9dim.py`, `backfill_actuarial_db_acb01.py`, `avshunter_db_update`). `avshunter_trap_engine.py` (Phase 5.5) is also missing. Findings that depend on these carry a confidence value.

---

## 1. Stage path as actually wired

`run_vanguard_pipeline` (`intelligent_orchestrator.py:3507-3614`) runs these steps:

1. `publish_cds3_discovery_worklist` (3253). This is a shadow/enforced publication of the Discovery ledger to `control_plane.sqlite`.
2. `prepare_cds3_governed_package_input` (3314). It returns `None` unless `AVSHUNTER_STAGE_GATING_ENFORCED`. When enforced, it writes `discovery_candidates_cds3_<run>.csv`, filtered to the worklist.
3. **Input mode.** `vanguard_input_mode()` (637-647) **defaults to `manifest`**. In that mode `_run_package_input_phases` (build_packages → inject_macro → backfill) is **skipped**, so those three scripts run only on the `packages` rollback path. In manifest mode the same builders are called in memory by `avshunter/c0_run/thin_package.py:165-208`.
   - Note: in manifest mode the CDS-3 governed CSV is **not** used. The manifest's `sources.discovery.path` decides, and it is written by `canonical_manifest.py`, which is not staged (confidence 60% on which file it cites).
4. `build_canonical_manifest.py`. This step is critical only in manifest mode.
5. `build_completed_market_profiles.py`, only if `completed_profile_stage_enabled()` (650). Otherwise the thin package falls back to the profile store, or to typed `NOT_EVALUATED` (`thin_package.py:210-231`).
6. Trap engine Phase 5.5 (non-critical; not staged).
7. `scripts/run_vanguard_from_packages.py --input-mode <mode>` (3602) → `vanguard.main.VanguardEngine`.
8. Downstream of the Vanguard stage, three steps consume its outputs:
   - `load_or_publish_descriptive_packet` (6015). It freezes C5 from Discovery plus the Vanguard CSV, and requires pass+reject rows to equal `packages_total`.
   - Options Intelligence.
   - Phase 8.5 `actuarial_enrichment_pass.run_actuarial_enrichment_pass` (6169-6211). It is non-critical and **runs after Options**. It reads `options/vanguard_signals_enriched_<run>.csv` first.

Config paths are at `intelligent_orchestrator.py:473-545`: `BUILD_PACKAGES`, `INJECT_MACRO`, `BACKFILL_TIMESERIES`, `BUILD_CANONICAL_MANIFEST`, `BUILD_COMPLETED_PROFILES`, `RUN_VANGUARD`, `ACTUARIAL_DB_PATH=C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet` and `ACTUARIAL_ENRICHMENT_PASS`.

### What actually reaches `VanguardInput`

This is the effective contract after the adapter; it matters for every finding below.

`run_vanguard_from_packages.build_orchestrator_like_payload` (655-889) builds a rich payload. `OrchestratorAdapter._build/_tech/_cal` (`orchestrator_adapter.py:141-284`) keeps **only** these fields:

- `ohlcv`
- `vwap_15m` (also reused as `vwap_daily`)
- `ema9/21/50/200` (from Discovery `EMA*`)
- `atr_current`
- `atr_history` (recomputed as a rolling mean of high−low, not true range)
- `adx`
- `rsi`
- `high_52w` / `low_52w`
- `wyckoff_phase` (Discovery raw phase letter)
- `compression_ratio`
- `macro_regime` (ignored later)
- `calendar.days_to_earnings`, which is never supplied, so it is always `None`
- `market_profile_evidence`
- `analysis_timestamp`, which is `datetime.now()` because the payload has no `as_of_utc` (165-167)

**Silently dropped:**

- `avshunter_signal`, which carries the Discovery tier, phase, intent, dominant_trend, control_state and signal_type. There is no `direction` inside it either.
- `intraday_position`, `control_dynamics`, `volume_profile_context`
- `wyckoff_phase_bucket`: `TechnicalData` has no such field, so the check at 233 is always False.
- `atr_percentile_rank`, `bb_width`, `bb_width_history`, `date_52w_high`, `date_52w_low`, `catalyst_proximity_override`
- the entire regime snapshot, apart from the vix fallback
- `macro_advisory`

`OptionsData()` and `MicrostructureData()` are empty. The macro input is replaced by `neutral_vanguard_macro_payload()` (`core_authority_policy.py:28`).

---

## 2. Module inventory (Task 1)

"PROD" means the module is reachable on the default Evening path. "ROLLBACK" means it is reachable only when `AVSHUNTER_VANGUARD_INPUT_MODE=packages`. "DEAD" means it is imported but its code is unreachable. "OFFLINE" means it is a CLI or research tool with no pipeline caller.

| Module | Purpose | Reach / caller | Inputs → Outputs |
|---|---|---|---|
| intelligent_orchestrator.py (3253-3614, 6169-6211) | Stage sequencing | PROD (evening workflow) | run_id, macro path → subprocesses; C5 packet; Phase 8.5 |
| scripts/build_packages_from_discovery.py | Discovery row → package dict (`discovery` = whole row, `contract_type` = row direction, `truth_packet` with identity `direction`, `actuarial` = DEFERRED) | ROLLBACK as a script; PROD as a library (`build_package`, `enforce_data_contract`, `read_discovery_csv`, `dedupe`, `locate_macro_snapshot` called by thin_package:172-175) | Discovery CSV and macro snapshot → `packages/*.package.json` and `index.json` |
| scripts/inject_macro_into_packages.py | Writes `macro`, `regime_snapshot` (6-field flat, `as_of_utc` = injection time), and the truth packet | ROLLBACK script; PROD library (`inject_macro_into_package`, thin_package:177) | package + runtime macro → package |
| scripts/backfill_timeseries_into_packages.py | Bars bounded by the completed session; appends a partial intraday bar in LATEST mode (719-738) | ROLLBACK script; PROD library (`attach_canonical_bars`, thin_package:200) | package + canonical DB or Polygon → `ohlcv_daily`/`daily_df`/`ohlcv`, `bar_data_as_of` |
| scripts/build_canonical_manifest.py | Writes `canonical_manifest.json` | PROD (critical in manifest mode) | run dir → manifest (the implementing module is not staged) |
| scripts/build_completed_market_profiles.py | Completed-session intraday profile | PROD only if the feature flag is on | canonical intraday bars → profile evidence stamps + store |
| market_structure/{profile,completed_profile,params}.py | TPO/value-area construction; direction-neutral | PROD via build_completed_market_profiles | bars → `MarketProfileEvidence` |
| market_structure/{service,lifecycle}.py | Double-distribution structure versus **governed_direction** | NOT on the Vanguard stage (morning_gate.py:3633-3730 only) | — |
| scripts/run_vanguard_from_packages.py | Real runner: DCV gate → governance routing → payload → adapter → engine → `signal_to_row` → physics → truth packet → behaviour state → CSVs | PROD | packages or thin packages → `vanguard/vanguard_signals.csv`, `vanguard_rejects.csv`, `vanguard_run_summary.json` |
| avshunter/c0_run/thin_package.py | In-memory package from manifest-cited sources | PROD (manifest mode default) | manifest, Discovery CSV, runtime macro, price DB (≤ evidence session), profile ledger → package dict |
| scripts/behaviour_state_builder.py | `behaviour_state_key`/hash (7 dimensions, **including direction**) and `catalyst_overlay` | PROD (runner:1555; enrichment pass) | row → key/hash |
| scripts/data_contract_validator.py | Hard OHLCV gate (≥ 50 bars, nulls, staleness against wall clock, regime present) | PROD | package → ok/reason, repair, annotate |
| scripts/macro_quant_packet.py (not on the list but on the path) | 75 macro CSV columns + ticker sector alignment | PROD | macro packet → row columns |
| contracts/core_authority_policy.py | Neutral macro payload; frozen-thesis-field assertion (not called in Vanguard) | PROD (payload only) | — |
| contracts/handoff_contract.py | Truth packet: carry groups, conflict rules, flat columns. The identity group includes `direction`, which is populated only if the row carries it | PROD (runner:1248, builders) | row → `truth_packet_*` columns |
| vanguard/main.py | Layer 1 → state → actuarial query → edge → actuarial classification; produces the verdict and recommendation | PROD | VanguardInput → VanguardSignal |
| vanguard/config.py | Thresholds, DB path, REQUIRED_ACTUARIAL_V6_COLUMNS | PROD | — |
| vanguard/integration/orchestrator_adapter.py | Payload → VanguardInput (fail-closed only on ticker, OHLCV and profile flag) | PROD | dict → VanguardInput |
| vanguard/schemas/input_schema.py | VanguardInput / TechnicalData / CalendarData … (**no direction field**; `avshunter_signal` optional and unused) | PROD | — |
| vanguard/schemas/auction_schema.py, state_outcomes_schema.py, trade_schema.py | Dataclasses. ActuarialOutcomes has 123 fields; EdgeAssessment.edge_direction is CALL/PUT/NONE | PROD | — |
| vanguard/schemas/vanguard_contract.py | Alternative strict VanguardInput v2 contract | DEAD/OFFLINE (no non-test importer) | — |
| vanguard/layer1_auction/auction_synthesizer.py | Governed completed-profile verdict: controller NEUTRAL, migration UNKNOWN, acceptance 0 | PROD. Lines 69-147 and all `_generate_scenarios/_assess_*/_determine_verdict` are **unreachable** (return at 63) | VanguardInput → AuctionVerdict |
| vanguard/layer1_auction/{market_profile,value_acceptance,control_identifier,value_migration}.py | Legacy synthetic auction (symmetric BUYERS/SELLERS logic) | Instantiated at synthesizer:36-39 but never called: DEAD | — |
| vanguard/layer2_statistical/state_calculator.py | StateVector (vol, trend, maturity, structure, catalyst, fixed macro, v2 buckets, 9-dimension match fields, hash) | PROD | VanguardInput + AuctionVerdict → StateVector |
| vanguard/layer2_statistical/actuarial_query.py | Loads the v7 parquet (subset of columns); match ladder EXACT → RELAXED → ANALOGUE → UNKNOWN; outcomes; calibration | PROD | StateVector → ActuarialOutcomes |
| vanguard/layer2_statistical/edge_detector.py | Gates 0-5, signal fast paths, **`_determine_direction`**, confidence, right-side score, bucket quality | PROD | state, outcomes, auction → EdgeAssessment |
| vanguard/layer2_statistical/scenario_builder.py | Byte-identical copy of the layer3 version | DEAD (not in the layer2 `__init__`) | — |
| vanguard/layer3_execution/scenario_builder.py, trade_builder.py | Multi-scenario trade plans; `target = price*(1+gain)` for PUT too | DEAD in Vanguard (main.py:16-17,110). The EIL imports `scenario_builder` top-level; its relative import fails, so the EIL uses an inline copy (execution_intelligence_runner.py:246-262). Confidence 85% | — |
| vanguard/core/actuarial_core_v7.py | Historical state and forward labels (the DB builder core) | OFFLINE (build scripts only) | daily OHLCV → observations |
| vanguard/core/actuarial_registry.py, schema_contract_v6.py, schema_guard.py, truth_packet.py, cache_integrity.py | Registry path/fingerprint; required canonical fields; truth-packet status/id; cache metadata. **Warning-only unless `AVSHUNTER_STRICT_ACTUARIAL_V6`** | PROD (runner lineage; enrichment pass) | — |
| vanguard/physics_state_engine.py | Deterministic "physics" fields and label; `physics_price_inputs` (PIT from the canonical sqlite, ≤ `bar_data_asof`) | PROD (runner:1246, 1532) | row → 23 physics columns |
| vanguard/trade_contract.py | Open/closed contract JSON store. `create_contract` has **no caller** in the repo | PROD (`list_open_tickers` at runner:1357) | — |
| vanguard/trade_governance.py | Q1-Q5 invalidation per open contract | PROD (runner:1462-1477) when an open contract exists | contract, price → HOLD/TIGHTEN/EXIT (mutates the contract file) |
| ev_engine_v2.py (repo root, v2.2.0) | EV v2; `EVInputs.direction="CALL"` default | PROD import from edge_detector:40; result is **discarded** (net_ev = actuarial EV20, lines 283-292) | — |
| vanguard/ev_engine.py, vanguard/ev_engine_v2.py (v2.1.0, identical to each other) | Older EV v2 | Not on the Vanguard stage. In the EIL, `vanguard/` precedes the root on sys.path, so the **EIL may load v2.1.0**. Confidence 75%; outside this stage | — |
| vanguard/ev_engine_v3.py, vanguard/ev3_stage0.py | Side-aware EV3 and a **mirrored CALL/PUT barrier sidecar** (target-first/stop-first/timeout/ambiguous) | Morning gate only (not the Vanguard stage); EV3 authority disabled | — |
| scripts/actuarial_enrichment_pass.py | Post-Vanguard 9-dimension cache lookup → `pkg["actuarial"]` or ledger | PROD, non-critical, after Options | enriched Vanguard CSV → packages / enrichment ledger |
| scripts/build_actuarial_v7.py, build_actuarial_v7_sharded.py | Staged parquet build; refuse to write the live path | OFFLINE | daily CSVs → staging parquet + build.json |
| domain/descriptive_forecast_handoff.py + contracts/descriptive_forecast_packet.py | C5 frozen packet; **reads Discovery `direction`** (CALL→BULL, PUT→BEAR); attaches Vanguard `layer1__auction_state` and `layer2__edge_quality` as context | PROD (orchestrator:6015), post-Vanguard | Discovery CSV + Vanguard CSVs → packet.json |
| domain/ticker_forecast.py | C5 value object with BULL/BEAR geometry invariants | PROD (via the C5 packet), Lab | — |
| domain/forecast_path_label.py | Mirrored BULL/BEAR first-passage label (same-bar → STOP_FIRST + flag, CENSORED reasons, signed survivor return) | OFFLINE (canonical_data/forecast_outcome_panel.py) | — |
| domain/competing_path_estimator.py | PIT Aalen-Johansen-style incidence with floors and block bootstrap | OFFLINE (no non-test caller) | — |
| domain/research_path_baseline.py | Unconditional non-overlapping price paths as known at cutoff | OFFLINE (no non-test caller in staged source) | — |

---

## 3. Direction / side inventory (Task 2)

Classification codes:

- **P**: produces a side.
- **D**: defaults a side.
- **U**: upside-only metric or label used as if side-neutral.
- **A**: asymmetric rule (bull branch without a bear mirror, or a mirror with the wrong sign).
- **T**: side keyed to the state trend rather than the assigned direction.
- **R**: reads Discovery direction.
- **X**: drops or ignores Discovery direction.
- **Z**: dead or unreachable code.

| # | file:line | Snippet | Cls | Missing mirror / note |
|---|---|---|---|---|
| 1 | layer2_statistical/edge_detector.py:503-534 | `_determine_direction` … `if score>15: "CALL" elif score<-15: "PUT" else … return "CALL"` (526/531/534) | P, D | Neutral evidence defaults to CALL. Under governed Layer 1 (NEUTRAL, UNKNOWN), score is only ±20 (prob_up_10pct) ±10 (trend), so the function reduces to: prob_up_10pct_20d > 0.55 → CALL; < 0.35 → **PUT**; else **CALL**. The PUT result is inferred from *absence of upside*, not from downside evidence |
| 2 | edge_detector.py:515-518 | `if outcomes.prob_up_10pct_20d > 0.55: +20 … < 0.35: -20` | U | Needs P(−10% first) |
| 3 | edge_detector.py:520-523 | `elif state.trend_direction=="DOWN" and outcomes.prob_trend_continues_20d > 0.60: score -= 10` | A (wrong-sign mirror) | `prob_trend_continues_20d` = P(20d return > 0) (actuarial_query:1102), so in a downtrend it adds a PUT vote when history went **up** |
| 4 | edge_detector.py:670-701 | `_bucket_edge_quality`: HIGH/EXTREME future momentum, `probability_edge≥0.10` → STRONG | U | `probability_edge` comes from the up-target (#12). The momentum bucket is magnitude-only; no side |
| 5 | edge_detector.py:283-295 | `net_ev = outcomes.expected_value_20d`; `win_rate = outcomes.win_rate` | U | Gate 5 uses long EV and P(ret > 0); the mirror is −EV and P(ret < 0) (`raw_prob_down_*` exists) |
| 6 | edge_detector.py:307-349 | CONTINUATION fast path `expected_value_10d > 0.0015`; TRANSITION `expected_value_20d > 0.002/0.003` | U | Same as #5 |
| 7 | edge_detector.py:82-89, 355 | `REGIME_EV_FLOORS` RISK_OFF higher than RISK_ON | A, Z | Unreachable: `state.macro_regime` is always TRANSITIONAL (state_calculator:810). **Contradicts** the earlier "RISK_OFF floors higher" as a live effect |
| 8 | edge_detector.py:408-446 | Trend-exhaustion veto: LATE+UP near the 52w high, or LATE+DOWN near the 52w low → NO_EDGE | T | Vetoes regardless of side. A PUT-at-top (UTAD/distribution) setup is killed as "LONG exhausted"; a CALL-at-bottom setup is killed as "SHORT exhausted" |
| 9 | edge_detector.py:268-276 | EVEngineV2 row: `expected_move_20d=median_gain_if_up`, `survival_prob=1-prob_down_5pct_before_up_10pct`, no `direction` → `EVInputs.direction="CALL"` (ev_engine_v2.py:33,190) | D, U, Z | Result discarded |
| 10 | edge_detector.py:569-593 | Right-side score: `prob_up_10pct_20d >0.60 or <0.30 +10`; RISK_ON & prob_up>0.5 +15; RISK_OFF & prob_up<0.40 +15; TRANSITIONAL & prob_up>0.45 +8 | U, A | Only the TRANSITIONAL branch is live, and it is bull-only (+8 for up-probability) |
| 11 | edge_detector.py:600-640 | Rationale "Win Rate: … probability of +10%", "Typical Win median_gain_if_up" | U | Text only |
| 12 | layer2_statistical/actuarial_query.py:666-673, 686-724 | `_target_col_for_horizon` → `outcome_hit_5pct_up_5d` / `7pct_up_10d` / `10pct_up`; baseline, raw, adjusted `prob_target_hit`, `probability_edge`, `probability_verdict` | U | Needs down-target columns |
| 13 | actuarial_query.py:715 | `raw_prob_stop_hit = mean(outcome_hit_5pct_down_before_10up)` | U (mis-specified) | True only when +10% was hit (core_v7:339), so it is not a stop probability |
| 14 | actuarial_query.py:718 | `raw_expected_time_to_target = median(outcome_days_to_10pct)` | U | Sentinel 20 for non-hits; upside only |
| 15 | actuarial_query.py:1100-1102 | `prob_up_10pct`, `prob_down_5pct` (before up), `prob_trend_cont = P(ret>0)` | U | "trend continues" is not keyed to the trend |
| 16 | actuarial_query.py:1104-1130 | `win_rate=P(ret>0)`(1113), `median_gain_if_up`, EV (1119), Kelly on prob_up_10pct (1125), `recommended_hold = median_days if prob_up_10pct>0.5 else 20` (1128) | U | Mirror: P(ret<0), median loss as gain, BEAR kelly and hold |
| 17 | actuarial_query.py:1150-1185 | 5d/10d `win_rate_Xd = P(ret>0)`, `prob_up_5pct_5d`, `prob_up_7pct_10d` | U | — |
| 18 | actuarial_query.py:708-713 | `raw_prob_down_5d/10d/20d = P(ret<0)` | (partial mirror) | The only mirrored side metric present; close-to-close only |
| 19 | actuarial_query.py:1061-1085 | `ret_pctl_{5,10,20}d_p01..p99` | neutral | Allows computing a side-correct close-to-close EV without the DB |
| 20 | actuarial_query.py:744-756 | `_signal_type_from_values`: CONTINUATION needs `location != "NEAR_HIGH"`; TRANSITION needs `location in (TRANSITION_ZONE, NEAR_LOW)` | A | No bearish mirror (NEAR_HIGH transition, NEAR_LOW continuation) |
| 21 | actuarial_query.py:396-408, 783-813 | `forward_momentum_confidence`, `momentum_tier` (future bucket > current) | neutral magnitude | Feeds edge TRADE fast paths |
| 22 | actuarial_query.py:1240-1340 | `_adjust_for_intraday_context`: AT_SUPPORT ×1.6/1.3, ACCUMULATION ×1.3, BUYERS ×1.2 → scales `prob_up`, `median_gain_if_up` | A, Z | Unreachable: `intraday_rows=0` always (state_calculator:353; VanguardInput has no attribute), and the adapter drops these fields |
| 23 | layer2_statistical/state_calculator.py:513-518 | Live trend: `ema21>ema50 & price>ema21 & adx>25` → UP, mirror DOWN | (symmetric) | Differs from the DB (`close>ema21>ema50>ema200`, no ADX) (core_v7:130-132) |
| 24 | state_calculator.py:520-533, 499-500 | Maturity LATE if <5% from the extreme; EARLY if the extreme is <30 days old. `date_52w_*` is never supplied → 365 → never EARLY | (symmetric; mismatch) | DB semantics are opposite: EARLY = ≥15% from the extreme (core_v7:136) |
| 25 | state_calculator.py:609-642 | Structure: +30 above both VWAPs, acceptance×40, +control. Governed → constant 25 → **WEAK** | A | "Above VWAP" is a bull criterion with no bear mirror. The DB's WEAK means RSI < 40 (core_v7:155), so every live row is matched to **bearish-momentum** history |
| 26 | state_calculator.py:862-883 | `_wyckoff_phase_bucket`: A/B/C → ACCUMULATION, D/E → MARKUP (letter only) | A | No MARKDOWN bucket; distribution-mode phases are mislabelled (SOR-001 §2 row 3) |
| 27 | state_calculator.py:553-563 | `early_candidate` = MID momentum and (MID_RANGE or NEAR_LOW) and EARLY_TRANSITION | A | Bull-only "before the herd" (mirror: NEAR_HIGH) |
| 28 | state_calculator.py:582-597 | `_sideways_maturity`: ACCUMULATION → SIDEWAYS_BUILDING | A | Distribution is not BUILDING |
| 29 | state_calculator.py:720-730 | Positioning bias NET_LONG/NET_SHORT | symmetric, Z (options empty → NEUTRAL) | — |
| 30 | core/actuarial_core_v7.py:141-152 | DB Wyckoff: DISTRIBUTION only near the highs; else **B/ACCUMULATION** fallback | A | Bearish trend rows become "ACCUMULATION"; no markdown |
| 31 | actuarial_core_v7.py:155 | `structure = STRONG if rsi>55 …` | (signed label) | A side-correct reading must treat STRONG as bull-aligned |
| 32 | actuarial_core_v7.py:153-154 | Sideways maturity BUILDING if ACCUMULATION | A | as #28 |
| 33 | actuarial_core_v7.py:158-168 | `phase_v2`, momentum, location, crabel | neutral | — |
| 34 | actuarial_core_v7.py:315, 325, 331 | `hit_5pct_up_5d`, `hit_7pct_up_10d`, `hit_10pct_up` | U | No `hit_*_down_*` |
| 35 | actuarial_core_v7.py:335-341 | `first_close_10` (close-based, default 20); `hit_5_before_10 = hit_10 and any(low ≤ −5% before first_close_10)` | U, bug | False whenever +10% is not hit. The high-based hit versus the close-based ordering is inconsistent; same-bar handling is not typed |
| 36 | actuarial_core_v7.py:342-349 | `days_to_10 / days_to_5 … else 20` | U | Sentinel; no down equivalents |
| 37 | actuarial_core_v7.py:350-353 | `outcome_category` BIG_WIN = ret ≥ 10% | U | Long P&L vocabulary |
| 38 | vanguard/main.py:247-255 | `edge_quality STRONG if EV20≥0.03 and prob_up_10pct_20d≥0.40` | U | — |
| 39 | main.py:357-366 | Exported quality promoted from bucket labels or `probability_edge≥0.10/0.05` | U | Up-target |
| 40 | main.py:372-396 | `edge_direction_label` → `"{CALL|PUT}_EDGE_STRONG_{h}"` | P (label) | A PUT label can carry strength derived from **upside** statistics |
| 41 | main.py:523 | `layer_2_result.edge_direction = edge.edge_direction` | P | Becomes `edge_direction` and `layer2__edge_direction` in the CSV |
| 42 | main.py:44-66 | `_select_preferred_horizon` by highest long EV | U | Also actuarial_query:731-740 |
| 43 | contracts/direction_governance.py:170-180 | `collect_resolution_evidence`: `vanguard_edge_direction`/`layer2__edge_direction`/`edge_direction` → family **ACTUARIAL**, weight 1.0 | consumes P/D | The CALL default and the "no-upside ⇒ PUT" output are admitted as independent actuarial evidence (downstream: OI:4707, eod_candidate_engine:1409, morning_gate:236) |
| 44 | direction_governance.py:216-222 | `directional_force ≥ 5` → PRICE_FLOW vote | consumes | From physics (#48); independent of edge_direction |
| 45 | scripts/run_vanguard_from_packages.py:768-785 | `avshunter_signal` carries tier/phase/intent/dominant_trend/control (no `direction`); `structural_target = entry_price` (mislabelled) | X | Dropped by the adapter anyway |
| 46 | run_vanguard_from_packages.py:697-716 | `dominant_event` substring map: `"up" in _de` → AT_RESISTANCE/BUYERS_STRENGTHENING before the `support` branch (so "support", "setup" and "Upthrust" map to BUYERS) | A, Z | Adapter drops the fields; #22 is unreachable |
| 47 | run_vanguard_from_packages.py:724-735 | Tier demotion if `dominant_trend=="BEARISH"` and no BUYER control | A, Z | No mirror for BULLISH + SELLER control on a PUT thesis. Affects only a local copy used for the dropped `avshunter_signal` |
| 48 | vanguard/physics_state_engine.py:208-219 | `directional_force` from return_5d/10d, trend (`layer2__trend_direction` → `dominant_trend`), vwap_bias, volume | P (signed) | Symmetric |
| 49 | physics_state_engine.py:221-245 | `force_alignment_score` includes `edge_direction` (CALL/PUT) and macro RISK_ON/OFF | consumes D | Vanguard's CALL default contaminates alignment |
| 50 | physics_state_engine.py:281-291, 363-365 | `phase_transition_probability` / `transition_success_*` from `layer2__adjusted_prob_target_hit` | U | Up-target feeds "transition success" for any side |
| 51 | physics_state_engine.py:294-329 | Labels COMPRESSED_BULLISH/BEARISH, CONTINUATION_UP/DOWN | symmetric | — |
| 52 | physics_state_engine.py:513-536 | `physics_forward_verdict(label, direction)` | symmetric | Used by the EIL only |
| 53 | scripts/behaviour_state_builder.py:117-133, 169 | `derive_direction` priority: direction, primary_direction, direction_bias, trade_bias, **selected_contract_side**, options_direction, **edge_direction**, trend_direction | P (dimension) | In `vanguard_signals.csv` rows only `edge_direction` exists, so the behaviour hash's direction dimension is Vanguard's CALL-default side. In Phase 8.5 (options-enriched CSV) it can be the option-selected side, which governance excludes as evidence |
| 54 | vanguard/trade_governance.py:239 | `direction = contract.get("direction", "CALL")` | D | — |
| 55 | trade_governance.py:242-262 | Q1 CALL below invalidation / PUT above | symmetric | — |
| 56 | run_vanguard_from_packages.py:1462-1477 | Open-contract ticker → governance → `continue` (no pass/reject row) | X / drop | Direction-agnostic drop; see §4 |
| 57 | build_packages_from_discovery.py:430-434, 385 | `contract_type = row.contract_type or row.direction`; `discovery = row` (incl. `direction`, `direction_authority`, `discovery_direction_status`) | R (carry) | Carried in the package only |
| 58 | build_packages_from_discovery.py:352-363; inject_macro:160-172 | Truth packet `direction` identity from the Discovery row | R | In the package JSON only |
| 59 | run_vanguard_from_packages.py:1486-1497, 1219-1244 | `_disc_row` copied, but only SCANNER and physics-source columns are copied to the row; `direction` is not | X | Vanguard CSV lacks `direction` |
| 60 | run_vanguard_from_packages.py:1160-1203 | Win-rate bridge seeds `win_rate_5/10/20d` from Discovery `win_probability` | U? | Discovery win_probability is side-unspecified (confidence 60% that it is long-framed) |
| 61 | scripts/actuarial_enrichment_pass.py:397-446, 697-751 | 9-dimension state from `layer2__trend_direction`, fallback `dominant_trend` (BULLISH/BEARISH vocabulary against UP/DOWN in the cache); lookup returns `win_rate_*`, `expected_move_*`, `avg_days_to_10pct` | U (confidence 70%; `lookup_state` not staged) | No direction key; no down metrics |
| 62 | domain/descriptive_forecast_handoff.py:125-138, 183-193 | Reads Discovery `direction` (CALL/PUT → BULL/BEAR); attaches `layer2__edge_quality` as `forecast_legacy_statistical_context` | R (correct); U (context) | Upside-derived edge_quality is shown beside BEAR forecasts |
| 63 | layer1_auction/auction_synthesizer.py:181-202 | `controller="NEUTRAL"`, `migration.direction="UNKNOWN"` | neutral by design | Makes #1 depend on #2 alone |
| 64 | auction_synthesizer.py:69-147, 336-429 | VWAP/POC reclaim trigger; "Breakout above VAH+2%" | A, Z | Bull-only triggers, unreachable |
| 65 | layer3_execution/scenario_builder.py:176-187, 303-311, 415-426 | PUT stop from VAH, but `target_1 = price*(1+gain)` | A, Z (bug) | PUT targets sit above spot |
| 66 | layer3_execution/trade_builder.py:48, 351-481 | Uses `edge.edge_direction`; CALL branches | Z | — |
| 67 | vanguard/schemas/state_outcomes_schema.py:196-249 | `prob_up_10pct_20d`, `prob_down_5pct_before_up_10pct`, `prob_up_if_buyers_control` / `prob_down_if_sellers_control` (never populated), `prob_continues_if_value_migrating_up` (no down twin) | U / A | — |
| 68 | ev_engine_v2.py:33, 190 | `direction:str="CALL"`; `ev_inputs_from_row` default CALL | D | Also used by the EIL |
| 69 | inject_macro_into_packages.py:120 | `regime_snapshot.dir_bias` (macro directional bias) | P (macro) | Ignored by the core (TRANSITIONAL); advisory only |

**Counts.** 69 inventory rows.

- 7 produce a side: #1, 40, 41, 48, 53, 69, and 57/58 (carry).
- 5 default to CALL: #1, 9, 54, 68, and 49 (consumes).
- 24 are upside-only metrics.
- 20 are asymmetric rules, including 3 wrong-sign or bug cases (#3, #13/35, #65).
- 1 is trend-keyed (#8).
- 4 read or carry Discovery direction, all outside the engine: #57, 58, 62, and the C5 packet.
- 3 drop direction: #45, 56, 59.
- 11 are dead or unreachable.

**No location in the Vanguard engine reads Discovery `direction`.**

---

## 4. Carry-through and row-dropping (Task 3)

- **Package:** yes. `pkg["discovery"]` holds the whole Discovery row, including `direction`, `direction_authority`, `discovery_direction_status` and `fusion_direction`. `pkg["contract_type"]` and `pkg["options_contract"]["contract_type"]` are set to the direction (build_packages:385, 407, 432). `pkg["truth_packet"]["direction"]` is also set. Thin packages are identical (thin_package:172).
- **VanguardInput:** no. There is no field for it (input_schema:186-224), and the adapter does not forward `avshunter_signal`.
- **vanguard_signals.csv:** no.
  - `signal_to_row` copies only `SCANNER_FIELD_NAMES` and 20 physics-source columns from `disc` (runner:1216-1244).
  - The truth packet's identity `direction` is populated only if the row has `direction`/`options_direction` (handoff_contract:515), and it does not.
  - The only side columns are Vanguard's own `edge_direction`, `layer2__edge_direction` and `layer2__outcomes__*` (no direction). `recommendation` embeds CALL/PUT, and `behaviour_state_key` has a direction dimension equal to edge_direction.
- **Veto, change or drop by direction:**
  - Nothing in the runner, the engine or physics filters rows on Discovery direction or on Vanguard's CALL/PUT. `edge_direction` changes labels only (recommendation, behaviour hash, physics alignment).
  - The trend-exhaustion gate (#8) sets `has_edge=False` by *trend*, not by side, but the row is still written.
  - **Drop hazard (confidence 85%).** When `vanguard/trades/open/*.json` exists for a ticker, the runner calls `evaluate_single`. The contract direction defaults to CALL, and the verdict mutates the contract file: `days_in_trade` increments on every rerun, and EXIT moves the file to closed/. The runner then `continue`s **without a pass or reject row**. `vanguard_run_summary.packages_total` still counts the ticker, so `load_or_publish_descriptive_packet` raises "Vanguard/Discovery population does not reconcile" (descriptive_forecast_packet.py:87-90). The orchestrator then **aborts the Evening run** (orchestrator:6026-6028). `create_contract` has no caller in the repo, so this is latent.
  - Tier demotion (runner:724-735) is keyed to BEARISH trend but affects only a dropped local copy (dead).

---

## 5. Output contract (Task 4)

### 5a. `vanguard/vanguard_signals.csv` (runner `write_csv`: sorted union of row keys, 1510-1537)

The legend marks **[DIR]** for direction-bearing fields, **[UP]** for upside-only or long-framed fields, and **[DFLT]** for fields that may be filled by defaults.

| Group | Columns |
|---|---|
| Identity / verdict | `ticker`, `timestamp` (wall clock [DFLT]), `verdict`, `final_recommendation` **[DIR]** (`CALL_/PUT_/STAT_EDGE_…`), `reasoning` |
| L2 headline | `state_hash`, `n_observations`, `win_rate_20d` [UP], `expected_value_20d` [UP], `confidence_level`, `has_edge` [UP-gated], `edge_direction` **[DIR]**, `failed_gate`, `no_edge_reason`, `schema_version`, `bucket_schema_version`, `debug_signature` (dimensions 5-9 from Discovery with FAR/MODERATE/MID/TRANSITIONAL defaults [DFLT]) |
| Lineage | `actuarial_source` (MISSING / V6_DB / DISCOVERY_FALLBACK), `actuarial_schema_version`, `actuarial_schema_fingerprint`, `actuarial_truth_packet_status`; `win_probability` (bridge only) [UP?] |
| Horizon | `win_rate_5d`, `win_rate_10d` [UP], `expected_value_5d/10d` [UP], `prob_up_5pct_5d` [UP], `prob_up_7pct_10d` [UP], `median_gain_if_up_5d/10d` [UP], `median_loss_if_down_5d/10d`, `median_max_drawdown_5d/10d`, `sharpe_ratio_5d/10d` [UP sign], `horizon_profile` (from long EV) [UP] |
| layer1__* | `ready_to_trade`, `confidence`, `auction_state`, `reasoning`, `profile__{poc,value_area_high,value_area_low,profile_type,balance,timestamp,timeframe}`, `acceptance__{level,score,classification,position_in_profile,…quality sub-dicts}`, `control__{controller,confidence,interpretation,aggression…}`, `migration__{direction,speed,consistency,magnitude,interpretation}` (`migration__direction` is market direction, always UNKNOWN) |
| layer2__* (main.py:419-566) | match audit: `state_match_{method,stage,dimensions,quality,similarity,is_exact}`, `sample_size`, `sample_confidence_bucket`, `preferred_horizon` [UP-selected], `confidence_penalty`, `confidence_weight`, `matched_state_key`, `original_state_key`, `fallback_reason`; calibration: `raw_prob_up_{5,10,20}d`, `raw_prob_down_{5,10,20}d` (mirror), `raw_prob_target_hit` [UP], `raw_prob_stop_hit` [UP, mis-specified], `raw_expected_return` [UP], `raw_expected_drawdown`, `raw_expected_time_to_target` [UP, sentinel], `baseline_probability` [UP], `adjusted_prob_target_hit` [UP], `adjusted_expected_return` [UP], `probability_edge` [UP], `probability_verdict` [UP]; 20d: `win_rate_20d`, `prob_up_10pct_20d`, `expected_value_20d`, `confidence_level`, `prob_down_5pct_first` [UP-conditional], `median_gain_if_up`, `median_loss_if_down`, `median_max_drawdown`, `kelly_fraction` [UP], `sharpe_ratio`, `recommended_hold_days` [UP]; 5d/10d duplicates; `ret_pctl_{5,10,20}d_p{01..99}` (39, side-neutral), `n_obs_{5,10,20}d`; edge: `has_edge`, `edge_direction` **[DIR]**, `edge_quality` [UP], `legacy_edge_quality` [UP], `failed_gate`, `no_edge_reason`, `edge_gate_has_edge`, `legacy_failed_gate`, `legacy_no_edge_reason`, `statistical_support_note`, `discovery_flag`, `bucket_edge_quality` [UP]; state: `vol_regime`, `trend_direction` (market), `trend_maturity`, `structure_quality`, `phase_v2`, `momentum_score`, `momentum_bucket`, `location_bucket`, `state_v2`, `early_candidate` [bull-framed], `transition_flag_v2`; forward: `future_momentum_bucket`, `…_distribution` (JSON-ish dict flattened), `…_confidence`, `…_sample_size`, `transition_flag_rate_v2`, `avg_{momentum,atr,adx}_delta`, `early_candidate_rate`; `layer2__outcomes__<123 ActuarialOutcomes fields>` (full dataclass, including `prob_up_if_buyers_control`, `prob_down_if_sellers_control`, `prob_continues_if_value_migrating_up`, `signal_type`, `momentum_tier`, `outcome_distribution__{BIG_WIN,…}` [UP vocabulary], `insufficient_data_reason`) |
| layer3__* | none (`layer_3_result=None`) |
| Macro quant (75) | `macro_packet_id` … `usmi_gamma_position` (see `MACRO_QUANT_CSV_FIELDS`), including `regime_distribution_bull/neutral/bear`, `ticker_sector_alignment(_score)` |
| Scanner passthrough (if present on the Discovery row) | the 30 `SCANNER_FIELD_NAMES` (handoff_contract:53-83) |
| Physics source passthrough | `vwap_bias`, `adx_14`, `atr_percentile`, `atr_percentile_rank`, `return_5d`, `return_10d`, `gap_pct`, `beta`, `physics_price_inputs_state`, `volume_ratio`, `crabel_compression`, `crabel_pattern`, `crabel_state`, `dominant_trend` [market dir], `sector`, `avg_volume`, `contract_spread_pct`, `spread_pct`, `iv_rank`, `iv_percentile` |
| Phase-2 baton | `phase2_baton_status`, `phase2_baton_issues` (plus defaulted `layer2__*` [DFLT]) |
| Physics (23) | `physics_state_id` (FORCE_BULL/BEAR bucket **[DIR-market]**), `market_energy_score`, `compression_energy`, `directional_force` **[DIR-signed]**, `force_alignment_score` (uses edge_direction), `trend_inertia`, `volatility_pressure`, `entropy_score`, `regime_instability_score`, `phase_transition_probability` [UP], `shock_sensitivity`, `liquidity_friction_score`, `hidden_state_label` [DIR-market], `state_transition_label` [DIR-market], `future_state_{5,10,20}d` [DIR-market], `transition_success_{5,10,20}d` [UP], `physics_data_quality`, `physics_defaulted_fields`, `physics_degraded_reason` |
| Truth packet | `truth_packet_status`, `truth_packet_conflict_count`, `…_warning_count`, `…_error_count`, `handoff_integrity_status`, `handoff_integrity_notes`, `verdict_coherence_status`, `verdict_coherence_notes`, plus carry-group fields already present in the row (re-emitted) |
| Behaviour | `catalyst_overlay`, `behaviour_state_key` **[DIR dimension = edge_direction]**, `behaviour_state_hash` |

`vanguard_rejects.csv` has `ticker`, `package_path`, `reason_code`, `reason_codes`, `error`, `exception_type` and `diagnostics`. `vanguard_run_summary.json` has `run_id`, `packages_total`, `passed`, `rejected`, `reject_top_reasons`, `output_csv` and `rejects_csv`.

### 5b. Actuarial enrichment pass output

The pass writes no CSV. It writes three things:

- `pkg["actuarial"]` in packages mode, or an append-only `actuarial` ledger record in manifest mode (enrichment_ledger)
- `index.json["actuarial_enrichment_pass"]` in packages mode
- a return dict to the orchestrator

| Group | Fields |
|---|---|
| Lookup (actuarial_enrichment_pass.py:716-747) | `available`, `actuarial_source`, `schema_version`, `schema_fingerprint`, `canonical_database_path`, `state_key`, `matched_key`, `fallback_depth`, `fallback_dims_dropped`, `sample_size`, `valid`, `no_match`, `penalty_multiplier`, `expected_move_{5,10,20}d` [UP likely], `win_rate_{5,10,20}d` [UP likely], `risk_10d`, `efficiency_10d`, `vol_10d`, `avg_days_to_10pct` [UP], `state_used` (9-dimension dict), `cache_built_at`, `cache_state_cols`, `actuarial_live_*`, `enriched_by`, `enriched_at`, `truth_packet_status`, `truth_packet_id` |
| Behaviour | `behaviour_state_key` **[DIR]**, `behaviour_state_hash`, `catalyst_overlay`, `actuarial_match_type`, `actuarial_ev_weight` |
| Carried | `HORIZON_FUTURE_FIELDS` (`future_momentum_bucket`, `preferred_horizon` [UP-selected], `horizon_bucket`, `future_path_label` (can be `outcome_category` [UP]), `return_5/10/20d`, `max_drawdown_20d`, `time_to_target_bucket`); `PHASE2_LAYER2_FIELDS` (35 keys) (`layer2__raw_prob_*`, `…probability_edge`, etc. [UP]), `phase2_baton`, `phase2_baton_status`, `phase2_baton_missing_fields` |
| Stamps | `enrichment_pass_attempted`, `enrichment_pass_result` (NO_VANGUARD_ROW path) |
| Summary | `packages_expected`, `packages_patched`, `missing_package_files`, `outcomes{EXACT_MATCH,FALLBACK_MATCH,NO_MATCH,NO_VANGUARD_ROW,LOOKUP_FAILED,ERROR_*}`, `usable_matches`, `match_rate`, `cache_states`, `cache_state_cols`, `schema_*`, `force_catalyst_none` |

The pass has no direction key and no down or side-specific metric.

---

## 6. Actuarial DB builder (Task 5)

**Labels produced by `actuarial_core_v7._forward_outcomes_arrays` (268-365).** Entry is `close[idx]` and the window is bars idx+1…idx+h.

| Label | Computation | Issue |
|---|---|---|
| `outcome_{5,10,20}d_return` | close[idx+h]/entry−1 | close-to-close, neutral |
| `outcome_max_gain_{5,10,20}d` | max(high)/entry−1 | neutral excursion |
| `outcome_max_drawdown_{5,10,20}d` | min(low)/entry−1 | neutral excursion (supports touch-only bear targets) |
| `outcome_hit_5pct_up_5d`, `outcome_hit_7pct_up_10d`, `outcome_hit_10pct_up` | max_gain ≥ x | up only; no ordering against the stop |
| `outcome_hit_5pct_down_before_10up` | `hit_10 and any(low ≤ −5% before first CLOSE ≥ +10%)`; `first_close_10` defaults to 20 | false whenever +10% is not hit; high/close inconsistency; the event-day low is excluded |
| `outcome_days_to_10pct`, `outcome_days_to_5pct` | first high ≥ x, **else 20** | sentinel treated as a value; up only |
| `outcome_category` | BIG_WIN … BIG_LOSS by 20d return | long vocabulary |
| `mature_{5,10,20}d` | enough future bars | good |
| `label_asof_date` | last bar date of the ticker file (build-level) | not per-label observation time |
| `calculation_version` | — | — |

State rows also carry `ticker`, `date` (decision session), `price`, raw features (`adx`, `rsi`, `atr_percentile`, `bb_percentile`, `dist_from_high/low`, `wyckoff_phase`), and `actuarial_core_hash`/`state_hash`. The build scripts add `source_name`, `source_dataset_fingerprint`, `source_adjustment_policy`, `build_id` and `built_at_utc`. The primary key is `(ticker, date, calculation_version)`.

**Lineage gap (confidence 85%).** `vanguard/config.py:268-291 REQUIRED_ACTUARIAL_V6_COLUMNS` requires columns that `build_ticker_observations` does not produce:

- `state_v2`, `momentum_score`
- `momentum_next`, `momentum_delta`, `atr_next`, `atr_delta`, `adx_next`, `adx_delta`
- `transition_flag_v2`, `future_momentum_bucket`

`actuarial_query` also reads `macro_regime`, `catalyst_proximity`, `horizon_bucket` and `early_candidate`. `VanguardEngine` refuses to start without the required columns (main.py:139-145), so the production parquet has been post-processed by out-of-repo scripts. Its forward "future bucket" columns are also forward labels, and their construction was not auditable here.

**Point-in-time filtering.**

- The parquet has `ticker` and `date`. `ActuarialQueryEngine` loads only `ACTUARIAL_QUERY_COLUMNS` (actuarial_query.py:53-95), which **excludes `ticker`, `date`, `mature_*`, `label_asof_date` and `build_id`**. No filter is therefore possible without changing the loader.
- The label availability date (the session idx+h) is **not stored**. It can be derived from the ticker's own bar sequence, which the builder has in memory; a calendar alone is not enough.
- Adjusted prices (`polygon_adjusted_true` / `upstream_adjusted_unverified`) embed later corporate actions.

**What mirrored BEAR labels would need.** Add them in the builder, which is the only place holding the ordered forward high/low/close arrays; the parquet has no forward bars.

1. Per side (BULL, BEAR) and horizon (5, 10, 20) with the geometry grid, a first-event label: `TARGET_FIRST | STOP_FIRST | NEITHER (event-free, fully observed) | AMBIGUOUS_SAME_BAR | CENSORED(reason: NOT_YET_OBSERVABLE | MISSING_SESSION)`, plus `event_session` (NaN, **not 20**), `gap_through` flag, and signed `survivor_return` (−return for BEAR). BEAR uses target `low ≤ entry·(1−t)` and stop `high ≥ entry·(1+s)`.
2. Reuse the existing conventions rather than inventing new ones:
   - `domain/forecast_path_label.label_forecast_path` for single geometry. It assigns a same-bar double touch to STOP_FIRST and flags it, and returns typed CENSORED.
   - `vanguard/ev3_stage0.classify_barrier_path` / `accumulate_ticker_barriers` (626-846) for grid form. It covers CALL/PUT, keeps AMBIGUOUS separate, and computes TIMEOUT only on horizon-mature rows.
   - Pick one owner: SOR-001 §3.3 says to reuse C12 semantics.
3. Touch-only down indicators (`hit_5pct_down_5d`, `hit_7pct_down_10d`, `hit_10pct_down_20d`) can be derived from the existing `outcome_max_drawdown_*` without a rebuild. Ordering or adverse-first cannot; it needs the rebuild.
4. Per-label `label_observed_session` (date of idx+h, or of the event), so that `label_available_at ≤ training cutoff` can be enforced. Also persist a bar-version or batch fingerprint.
5. Keep v7 untouched and write `actuarial_v8`/episode panel columns under a new `calculation_version`. Update `REQUIRED_*`, `ACTUARIAL_QUERY_COLUMNS` and `_target_col_for_horizon` per side.

---

## 7. Point-in-time / leakage inventory and "missing treated as measured" (Task 6)

### 7a. PIT / leakage

| # | file:line | Issue |
|---|---|---|
| L1 | actuarial_query.py:53-95, 229-245 | The DB is loaded without `ticker`/`date`; no `as_of` cutoff; no embargo. The query cohort can include rows whose forward labels postdate the evidence session in replays, and the same ticker's overlapping recent windows |
| L2 | actuarial_query.py:689-693 | `baseline_probability`/`baseline_return` are computed over the **entire DB** (all dates and tickers) |
| L3 | state_calculator.py:855-893 (hash excludes ticker); actuarial_query | Universe-pooled statistics presented per ticker; no effective-sample or dependence correction (`confidence = min(1, n/50)`, actuarial_query:1130) |
| L4 | actuarial_query.py:861-871 | `sample_size` and the EXACT threshold count include immature rows; outcomes later `dropna` (n differs) |
| L5 | state_calculator.py:499-500 | `pd.Timestamp.now()` minus `date_52w_high` (the value is always None → 365 constant) |
| L6 | state_calculator.py:664-683 | Relative-volume partial-day scaling uses `datetime.now()` UTC hour. The result depends on run time (liquidity, `volume_bucket`, state confidence) |
| L7 | state_calculator.py:492, 602; runner:449-459 | `ohlcv.iloc[-1]` is the current bar. In LATEST packages mode it is a partial intraday bar (backfill:719-738; `intraday_partial` flag not read by Vanguard). Manifest mode is bounded to the evidence session (thin_package:188-197) |
| L8 | orchestrator_adapter.py:162-167 | `analysis_timestamp = now()`, so `timestamp` in the CSV is the wall clock, not the evidence session |
| L9 | inject_macro_into_packages.py:110-122 | `regime_snapshot.as_of_utc` is stamped with injection time ("staleness gate always sees a fresh timestamp") |
| L10 | data_contract_validator.py:204-212; backfill:391, 614 | Staleness is judged against the wall clock, so replays are non-deterministic |
| L11 | runner:672, 790-793 | `current_price` and EMAs come from Discovery (Discovery's time), while bars come from the canonical store. There is no consistency check between `stock_price` and the last close |
| L12 | actuarial_core_v7.py:90-106, 305 | Builder features are causal (rolling/EWM, rank window includes the current row). `label_asof_date` is file-level; adjusted prices introduce look-ahead of corporate actions |
| L13 | actuarial_enrichment_pass.py | Uses the cache built by an out-of-repo builder; unknown PIT |
| L14 | main.py:44-66; actuarial_query:352-356 | `preferred_horizon` is chosen *after* seeing sample outcomes (selection on the same sample used to report the edge) |
| L15 | auction_synthesizer.py:213 | `_not_evaluated` profile timestamp = now |
| (OK) | physics_state_engine.py:460-505 | `physics_price_inputs` is PIT-correct (≤ `bar_data_asof`) |

### 7b. Missing treated as measured

| # | file:line | Missing → value |
|---|---|---|
| M1 | orchestrator_adapter.py:244-251 | `ema*` → 0.0, `adx` → 0.0, `rsi` → 50. With EMAs 0 the trend becomes SIDEWAYS |
| M2 | runner:866-870 | `adx = (adx_14 or calc) if len>20 else 0.0`: operator precedence, so Discovery `adx_14` is ignored when bars ≤ 20 |
| M3 | runner:806 | `rsi = 50.0` if ≤ 14 bars |
| M4 | state_calculator.py:432, 386-397 | `iv_percentile` 50 (no IV field) → the IV-spike veto never fires |
| M5 | state_calculator.py:755-761 | No earnings date → proximity NONE, `days_since=90` → both earnings vetoes dead (edge_detector:466-484) |
| M6 | state_calculator.py:614-642 | `vwap_1h` 0 and acceptance 0 → structure score 25 → **WEAK** for every ticker (refines the earlier "capped at 40": 40 is reachable only if `vwap_1h` were supplied) |
| M7 | state_calculator.py:807-812 | macro → TRANSITIONAL, vix percentile 50 |
| M8 | state_calculator.py:257-268 | `crabel_state` proxy always (no Discovery field reaches it); `horizon_bucket` → MEDIUM |
| M9 | state_calculator.py:499 | `date_52w_*` None → 365 → maturity can never be EARLY |
| M10 | orchestrator_adapter.py:209-214 | 52w high/low from **close** if missing (runner supplies high/low, so rarely used) |
| M11 | actuarial_query.py:485-530, 861 | UNKNOWN/NONE match values (e.g. `crabel_state=NONE`, `wyckoff=UNKNOWN`) are dropped from the dimensions; still `is_exact=True`, similarity 1.0 |
| M12 | actuarial_query.py:162-194 | `_empty_outcomes` gives probabilities/EV = 0.0 with n=0 (reads as measured zero) |
| M13 | actuarial_query.py:1107-1123 | No winners → `median_gain=0.05`; no losers → `median_loss=−0.03`; `avg_win 0.05`, `avg_loss 0.03`; Kelly 0.1 fallback |
| M14 | actuarial_query.py:1135-1175 | 5d/10d metrics 0.0 when columns are absent |
| M15 | actuarial_query.py:680-701 | `_mean_numeric` default 0.0 for a missing target column (baseline 0 → positive "edge") |
| M16 | runner:245-297 | Phase-2 baton: missing `layer2__*` → 0.0 probabilities, `NO_STAT_EDGE`, penalty 0.30 (flagged by `phase2_baton_status`) |
| M17 | runner:1160-1176 | Deferred actuarial (always at Vanguard time) plus n>0 → relabelled `actuarial_source=V6_DB`, `truth_packet_status=VALID` with the **registry** fingerprint (asserted, not validated) |
| M18 | runner:1178-1203 | No win rates → Discovery `win_probability` clamped [0.30, 0.80] seeds `win_rate_5/10/20d` |
| M19 | runner:931-958, 1089-1097 | `debug_signature` dimensions default FAR/MODERATE/MID/TRANSITIONAL |
| M20 | runner:871 | `atr_percentile_rank` default 50 (dropped by the adapter anyway) |
| M21 | edge_detector.py:266-280 | EV2 inputs `runway_pct 2.0`, `delta .40`, `iv .50`, `breakeven_pass_live True` (discarded result) |
| M22 | edge_detector.py:190-191 | `positional_strategy` default True disables the intraday penalty |
| M23 | actuarial_enrichment_pass.py:494-521, 457-476 | `atr_pct` missing → MID; adx missing → ""; catalyst forced NONE; `dominant_trend` BULLISH/BEARISH used as `trend_direction` |
| M24 | physics_state_engine.py:168-186 | Neutral defaults (50/25/1.0/0.08) — **flagged** `DEGRADED_DEFAULTS` (good) |
| M25 | schema_guard.py:150-156; truth_packet.py:265-269; cache_integrity.py:371-374; runner:1017 | Contract and fingerprint failures are warnings unless strict; the runner ignores the `validate_truth_packet` result |
| M26 | trade_governance.py:234-236, 272-274 | No price or state → PASS ("cannot evaluate, holding") |
| M27 | adapter:263 | `vix` → 20 |

---

## 8. Re-verification of previously reported findings

| Prior finding | Status |
|---|---|
| VanguardInput has no direction field; `avshunter_signal` unused | **Confirmed**, and stronger: the adapter never even sets `avshunter_signal` (orchestrator_adapter:173-188) |
| `_determine_direction` returns CALL default (~534); consumed as ACTUARIAL evidence | **Confirmed** (503-534; direction_governance:170-180). New: under governed Layer 1 it reduces to a threshold on `prob_up_10pct_20d` (PUT when < 0.35), and the DOWN-trend vote has the wrong sign (#3) |
| Actuarial outcome columns upside-only (core_v7 ~310-346); `hit_5pct_down_before_10up` only true when +10 hit; days_to_10pct=20 sentinel | **Confirmed** (315-349). Additionally, `days_to_5pct` has the same sentinel, and `hit_5_before_10` mixes a high-based hit with close-based ordering |
| win_rate=P(ret>0) (~1113), recommended_hold (~1128) | **Confirmed** (1113, 1128) |
| Missing match dimensions dropped but tagged EXACT (~525, 836, 864) | **Confirmed** (525, 861-871). Partly visible via `state_match_dimensions` |
| Live structure_quality capped at 40=WEAK vs DB WEAK=rsi<40 | **Confirmed/refined:** effectively a constant 25 → WEAK for all rows |
| Live trend definitions differ from DB | **Confirmed**, plus trend_maturity has **opposite EARLY semantics** and live can never be EARLY |
| Adapter defaults missing ema/adx/rsi to 0/50 | **Confirmed** (244-251) |
| Edge gates use long EV | **Confirmed** |
| RISK_OFF floors higher | **Contradicted as a live effect:** macro is fixed TRANSITIONAL (state_calculator:807-812), so RISK_* branches are unreachable |
| Trend-exhaustion veto keyed to state trend | **Confirmed** (408-446) |
| Pooled universe-wide stats presented per ticker | **Confirmed** (ticker not loaded or hashed) |
| No PIT cutoff, iloc[-1] partial bar, Timestamp.now() | **Confirmed**. The partial bar applies only in the LATEST/packages path; the manifest default is session-bounded |
| Earnings veto never fires; iv_percentile default 50 | **Confirmed** |
| Quality promotion from up-target edge | **Confirmed** (main:362-365; edge_detector:694-697) |
| Governed Layer 1 hard-codes NEUTRAL/UNKNOWN | **Confirmed** (181-187) |
| Completed-profile flag | **Confirmed** (orchestrator:650-654); the thin package falls back to the store or NOT_EVALUATED |
| Dead bullish code in auction_synthesizer/scenario_builder (PUT targets above spot) | **Confirmed** (auction_synthesizer:69-429 unreachable; scenario_builder:186-187, 310-311, 425-426) |

**New items not previously reported:**

- Default input mode is manifest, so the package scripts are rollback-only.
- The adapter drops most payload fields, including `wyckoff_phase_bucket`, intraday context and dates.
- `_adjust_for_intraday_context` is unreachable.
- The prob_trend_continues sign error.
- The PUT signal comes from the absence of an upside move.
- The governance `continue` can make the C5 packet fail to reconcile and abort the Evening run.
- A bare DB lineage built with `actuarial_core_v7` cannot pass `REQUIRED_ACTUARIAL_V6_COLUMNS`.
- The behaviour-hash direction dimension equals Vanguard's CALL default.
- `physics.force_alignment` uses edge_direction; `phase_transition_probability` uses the up-target probability.
- The lineage relabel to V6_DB/VALID is asserted, not validated.
- Discovery `adx_14` is ignored when bars ≤ 20 (operator precedence).
- `dominant_event` substring mapping error (dead).
- The EIL loads EV v2.1.0 rather than v2.2.0 (confidence 75%).
- `market_structure.service` (governed_direction) is Morning-only.

---

## 9. Design hooks (evidence-based, not a design)

- **Direction-assignment input point.** Add `assigned_direction ∈ {CALL, PUT, UNRESOLVED, STRANGLE}` plus provenance to `VanguardInput` and pass it through the adapter. The source already exists in `pkg["discovery"]["direction"/"direction_authority"/"discovery_direction_status"]`, and in both modes. Echo it in `signal_to_row` as `discovery_direction` (never overwritten).
- **Remove `_determine_direction` as an evidence producer.** Replace it with per-side evidence blocks `bull_*` and `bear_*` (and `side_evaluated`). Then `direction_governance`'s ACTUARIAL family must read a side-specific support field, not `edge_direction`.
- **Side-correct metrics available without a DB rebuild** (close-to-close and touch only): P(ret<0) (`raw_prob_down_*`), signed EV from `ret_pctl_*`, and touch-down from `outcome_max_drawdown_*`. Target-first, adverse-first, event-free and censored metrics require the builder change in §6.
- **Gates needing per-side versions:** #5, 6, 8, 10, 20, 27, 28, 38, 39, 50. Items #7, 22, 46, 47, 64, 65 are dead and can be deleted or quarantined, with tests proving no regression.
- **Match-contract repairs are prerequisites** (otherwise side-correct metrics are computed on mismatched cohorts): M6/#25 structure, #24 maturity, #23 trend, #26/#30 Wyckoff, M11 dimension dropping, L1 PIT loader.
