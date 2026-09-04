# AVSHUNTER Pipeline Functional Audit
**Date:** 2026-06-30  
**Auditor:** Claude Sonnet 4.6 (read-only forensic review)  
**Version:** intelligent_orchestrator.py v3.2.1 (built 2026-05-03)  
**Classification:** INTERNAL — PROPRIETARY

---

## 1. Executive Summary

AVSHUNTER is a proprietary, advisory-only systematic options trading pipeline running live on Tastytrade with a $50,000 account, max 5 positions. It does not place trades autonomously; it produces ranked option-trade candidates for human execution review. The pipeline has two run modes: an **evening workflow** (post 16:15 ET, EOD bar data) that builds the full candidate slate, and a **morning workflow** (09:45 ET, live data) that validates whether EOD candidates remain executable. The architecture consists of approximately 95 Python modules organised into 12-plus logical phases across discovery, structural scoring, options intelligence, risk-layer enrichment, and execution gating. Three major scoring phases were decommissioned between April and May 2026 (SuperBrain as a decision engine, the Execution Decision Engine at Phase 9.5, and the Enhancement Layer at Phase 9B), leaving the pipeline leaner but with some commented-out orchestrator wiring that creates navigation risk. The Position Sizing Engine (PSE) is retired and always returns pse_final_size=0.0, meaning all sizing is manual. Sprint 1 (Exit Discipline Engine) and Sprint 3 (Trap-to-Launch Engine) are deployed and wired. Sprint 2 (Convexity Strike Map) and Sprint 4 (ML Feedback Loop) are NOT YET BUILT.

---

## 2. Architecture & Phase Spine

### Evening Workflow (full rebuild, ~3,000-6,500 tickers)

```
┌──────────────────────────────────────────────────────────────┐
│  Phase 0: Universe Scanner Consumer                          │
│    merge_scanner_inputs() + build_augmented_universe()       │
│    write_scanner_context()                                   │
├──────────────────────────────────────────────────────────────┤
│  Phase 0 Preflight: run_preflight_checks()                   │
│    universe gate · macro JSON validation                     │
├──────────────────────────────────────────────────────────────┤
│  Pre-Discovery Setup:                                        │
│    sector_alignment.py (REQUIRED for live capital)           │
│    scripts/normalise_macro_contract.py  (FIX-04)            │
│    bond_macro_state.json sidecar merge                       │
│    merge_macro_enrichment_into_macro_latest()                │
│  Phase 4.6: Actuarial Cache Builder (vanguard/)              │
│  Phase 4.7a: Actuarial Transition Matrix Builder             │
│  Phase 4.7b: Regime Screener (avshunter_regime_screener.py)  │
├──────────────────────────────────────────────────────────────┤
│  PHASE 1 (orchestrator label) / Phase 3 (CLAUDE.md)         │
│  Discovery: avshunter_discovery_ULTIMATE.py                  │
│    Tiers 0/1/2/3 · Wyckoff · Crabel · swing_fusion          │
│    Output: discovery_candidates_ultimate_{run_id}.csv        │
│    External Intel Review Lane → same CSV                     │
│    Macro Enrichment stamp → same CSV                         │
├──────────────────────────────────────────────────────────────┤
│  PHASE 2: Quality Validation + Regression Check              │
│  PHASE 4: Position Tracking (position_lifecycle_tracker.py)  │
│  PHASE 4.5: Pin Run Directory + macro_snapshot.json          │
├──────────────────────────────────────────────────────────────┤
│  PHASES 5–8: VANGUARD PIPELINE                               │
│    5a: Build Packages from Discovery                         │
│    5b: Inject Macro into Packages                            │
│    5c: Backfill Timeseries into Packages                     │
│    5.5: Trap-to-Launch Engine (avshunter_trap_engine.py)     │
│         Writes tle_ fields into package JSONs                │
│    6:  Run Vanguard (run_vanguard_from_packages.py)          │
│         Writes vanguard_signals.csv                          │
├──────────────────────────────────────────────────────────────┤
│  Phase 8a PRE: Catalyst Truth Engine (pre_options stage)     │
│  Position Lock Check (trade_journal → locked_tickers.txt)    │
│  Phase 8b: Options Intelligence                              │
│    scripts/avshunter_options_intelligence.py v1.1            │
│    Input: discovery_csv + vanguard_signals.csv               │
│    Output: options_intelligence_{run_id}.csv                 │
│             vanguard_signals_enriched_{run_id}.csv           │
│  Phase 1B: Macro Horizon Router (run_horizon_router)         │
│    Patches horizon_bucket into OI CSV                        │
│  Phase 8a POST: Catalyst Truth Engine (post_options stage)   │
│  Phase 8.5: Actuarial Enrichment Pass                        │
│    scripts/actuarial_enrichment_pass.py                      │
│    Patches actuarial fields into package JSONs               │
│  Phase 7.5: Phantom Scoring Engine                           │
│    scripts/phantom_engine.py                                 │
│    Output: options_intelligence_phantom_{run_id}.csv         │
│  Phase 8c: Core Intel Exporter                               │
│    scripts/core_intel_exporter.py                            │
│  Phase 8.6 (packages): Trigger Layer                         │
│    trigger_layer.patch_run_packages() → package JSONs        │
│  Phase 8d: SuperBrain PASSTHROUGH                            │
│    Copies OI → superbrain_enriched_{run_id}.csv              │
│    Maps options_verdict → sb_final_verdict                   │
│    (SuperBrain scoring deprecated 2026-04-28)                │
│  Patch horizon → superbrain_enriched                         │
│  Phase 8b (stub): Catastrophe Gate — NO-OP since Sprint 2   │
│  Phase 8e: Wall Break Scorer                                 │
│    wall_break_scorer.py → wall_break_scores_{run_id}.csv     │
│  FIX-ACTUARIAL-SEQ: Pre-EIL actuarial injection             │
│    Reads package JSONs → patches superbrain_enriched         │
├──────────────────────────────────────────────────────────────┤
│  Phase 9: Execution Intelligence Layer (EIL)                 │
│    execution_intelligence_runner.py v4.1                     │
│    5 strategies: liquidity, IV distort, GEX flip, OBI, POC  │
│    PSE sizing (RETIRED: pse_final_size always 0.0)           │
│    Output: eil_enriched_{run_id}.csv                         │
│             execution_v3_5_{run_id}.csv                      │
│  inject_actuarial_into_eil_csv (safety net)                  │
│  Phase 10a: GARCH Runner → garch_forecasts_{run_id}.csv      │
│  Phase 10b: GARCH merge → superbrain + eil + execution CSVs  │
│  Phase 8.6b: Trigger Layer → EIL CSV enrichment             │
│    enrich_csv(eil_enriched, inplace=True)                    │
│  Handoff Conflict Guard                                      │
│  [Phase 9.5 EDE — COMMENTED OUT, decommissioned May 2026]   │
│  [Phase 9B Enhancement — COMMENTED OUT, decommissioned]     │
│  [Phase 9C Trade Book Builder — COMMENTED OUT]              │
│  Post-EIL: Catalyst Truth Engine                             │
│  Phase 9D: McMillan Advisory Layer                           │
│    mcmillan_advisory_layer.py enriches eil_enriched          │
├──────────────────────────────────────────────────────────────┤
│  Phase 10: EOD Candidate Engine                              │
│    eod_candidate_engine.py v1.3                              │
│    Input: eil_enriched + WBS + discovery + vanguard          │
│    Output: morning_candidates_{run_id}.csv                   │
│    B1 FIX: contract fields from OI CSV                       │
│    B4 FIX: l3_ GARCH fields                                  │
│    McMillan handoff join                                     │
│    Macro Exposure Resolver (display only)                    │
│    B3: exit_rules_engine.py (scripts/)                       │
│  Write latest.json                                           │
│  Pipeline Integrity Report                                   │
│  Dropoff Audit · Handoff Contract Audit · UAT Audit Report  │
│  Lab Control: final_run_manifest.json + triage CSV          │
│  Archive + Prune + Report                                    │
│  Stage 9: Outcome Capture                                    │
│  Stage 10: Weekly Intelligence Report (Sundays only)         │
└──────────────────────────────────────────────────────────────┘
```

### Morning Workflow (09:45 ET, live data)

```
Resolve run_id (CLI arg OR data/output/latest.json)
  ↓
Catalyst Truth Layer (pre_morning_validation)
  ↓
morning_gate.run_morning_gate()          [morning_gate.py v1.2]
  CHECK 1: Invalidation intact (BLOCK if fails)
  CHECK 2: Macro regime unchanged (FLAG)
  CHECK 3: Contract liquid (FLAG)
  CHECK 4: Bond macro clear (FLAG)
  CHECK 5: Layer 3 model risk clean (FLAG)
  Output: morning_validated_trades_{run_id}.csv
  ↓
[Exit Engine hook]
  avshunter_exit_engine.py
  Output: morning_exit_signals.csv
  ↓
execution_gate.run_execution_gate()      [execution_gate.py v1.1]
  spread ≤8%, delta 0.30–0.60, IV ≤60%, runway ≥1.5%
  ↓
Lab/Interpreter handoff
  contracts/lab_control.write_final_run_manifest()
  contracts/lab_control.write_final_opportunity_book()
  pipeline_interpreter/ma_inputs_sync.sync_file()
```

---

## 3. Phase-by-Phase Inventory

| Phase | Name / Path | Purpose | Key Inputs | Key Outputs | Decisions/Gates | Status |
|-------|-------------|---------|-----------|------------|-----------------|--------|
| 0 | Universe Scanner Consumer (`intelligent_orchestrator.py:3310`) | Merge VMS scanner + manual uploads into augmented universe | VMS dropbox, manual uploads | `augmented_universe_{run_id}.csv`, `scanner_context_{run_id}.json` | None (informational) | LIVE |
| 0-PF | Preflight (`run_preflight_checks`, line 1037) | Universe gate, macro JSON validation | Universe CSV, macro JSON | `macro_path` returned | **HARD ABORT** if universe empty or macro missing | LIVE |
| Pre-D1 | Sector Bias Map (`scripts/sector_alignment.py`) | Injects tailwind/headwind sector tags | macro JSON | `_sector_bias_map` dict | **HARD ABORT** if missing and `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT=true` | LIVE |
| Pre-D2 | Macro Normaliser (`scripts/normalise_macro_contract.py`, FIX-04) | Adds 4 structured scores: net_liquidity_score, vix_regime_score, gex_regime_score, macro_momentum_score | macro JSON | Updated macro JSON | Manifest set to `REVIEW_ONLY_MACRO_DEGRADED` if fails | LIVE |
| Pre-D3 | Bond Macro Sidecar | Merges curve_state, credit_stress, zn_direction, auction_spread_risk | `dropbox/macro/bond_macro_state.json` | Updated macro JSON `.extras.bond_macro` | Non-critical | LIVE |
| Pre-D4 | Macro Enrichment Merge | Merges GPT enrichment delta into macro | `dropbox/macro/avshunter_macro_enrichment_delta.json` | Updated macro JSON | Non-critical (context only) | LIVE |
| 4.6 | Actuarial Cache Builder (`vanguard/actuarial_cache_builder.py`) | Builds actuarial cache parquet from actuarial DB | `actuarial_database_v6.parquet` (vanguard dir) | `actuarial_cache.parquet` | Non-critical | LIVE |
| 4.7a | Actuarial Transition Matrix Builder | Reads actuarial DB, writes phase-to-phase probabilities | Actuarial DB | `transition_matrix_*.csv` | Non-critical | LIVE |
| 4.7b | Regime Screener (`avshunter_regime_screener.py`) | Supplements discovery with mean-reversion, vol expansion, structural breakout signals | Discovery CSV, macro JSON | `regime_signals_{run_id}.csv` | Non-critical | LIVE |
| 1/3 | Discovery (`avshunter_discovery_ULTIMATE.py`) | Universe scan, Wyckoff/Crabel scoring, tier assignment | `polygon_liquid_universe.csv`, Polygon API, scanner_context | `discovery_candidates_ultimate_{run_id}.csv`, `discovery_summary_{run_id}.json`, `early_positions_{run_id}.csv` | **HARD ABORT** if fails | LIVE |
| 2 | Quality Validation | Candidate ratio + tier distribution check | discovery summary JSON | Logs + abort condition | **HARD ABORT** if ratio outside bounds | LIVE |
| 3 | Regression Detection | Compare to previous run candidate count | Previous summary JSON | Log warning if >50% swing | Warning only (non-blocking) | LIVE |
| 4 | Position Tracking (`position_lifecycle_tracker.py`) | Track open position lifecycle | Trade journal | Position log | Non-critical | LIVE |
| 4.5 | Pin Run Directory | Create per-run dir, stage macro snapshot, validate contract_version | macro JSON | `run_meta.json`, `macro_snapshot.json`, `macro_quant_packet.json`, `truth_packet_run.json` | **HARD ABORT** if can't write or contract mismatch | LIVE |
| 5a | Build Packages (`scripts/build_packages_from_discovery.py`) | Build per-ticker package JSONs from discovery CSV | `discovery_candidates_ultimate_{run_id}.csv` | `*.package.json` in `packages/` | **HARD ABORT** if fails | LIVE |
| 5b | Inject Macro (`scripts/inject_macro_into_packages.py`) | Stamp macro regime into each package JSON | Macro JSON, packages | Updated packages | **HARD ABORT** if fails | LIVE |
| 5c | Backfill Timeseries (`scripts/backfill_timeseries_into_packages.py`) | Fetch/stage OHLCV time-series into packages | Polygon/MarketData APIs | Updated packages | Returns code 2 for partial (allowed to continue) | LIVE |
| 5.5 | Trap-to-Launch Engine (`avshunter_trap_engine.py`) | Detect bullish/bearish traps, write tle_ fields to package JSONs | Package JSONs (discovery fields) | `tle_` fields in package JSONs | Non-critical, fail-open | LIVE (Sprint 3) |
| 6 | Vanguard (`scripts/run_vanguard_from_packages.py`) | Full statistical vanguard scoring of packages | Package JSONs, actuarial cache | `vanguard_signals.csv`, `vanguard_run_summary.json` | **HARD ABORT** if fails | LIVE |
| 8a-pre | Catalyst Truth Engine (`catalyst_truth_engine.py`, pre_options) | Shadow advisory enrichment for catalyst quality before OI | Run artifacts, `dropbox/inputs/catalyst_calendar_latest.csv` | `catalyst_` fields patched into artifacts | Non-critical | LIVE |
| 8b-lock | Position Lock Check (line 2453) | Read open positions → write `locked_tickers_{run_id}.txt` | `avshunter_trade_journal.py` | Lock file | Non-critical | LIVE |
| 8b | Options Intelligence (`scripts/avshunter_options_intelligence.py` v1.1) | Contract selection, greeks, OI, PCR, gamma flip, structural EV | Discovery CSV, vanguard_signals.csv | `options_intelligence_{run_id}.csv`, `vanguard_signals_enriched_{run_id}.csv` | Non-critical; verdicts: EXECUTE / ARMED / STAND_DOWN | LIVE |
| 1B | Macro Horizon Router (`macro_horizon_router.py`, `run_horizon_router` line 1163) | Route each signal to 1-5D / 6-10D / 11-20D / blocked | OI CSV, macro JSON | `horizon_{bucket}_{run_id}.csv`, `horizon_summary_{run_id}.json` | Size multiplier (0x=blocked to 1.0x=full); patches into OI CSV | LIVE |
| 8a-post | Catalyst Truth Engine (post_options) | Second pass catalyst enrichment after OI | Same inputs | Patches catalog truth fields | Non-critical | LIVE |
| 8.5 | Actuarial Enrichment Pass (`scripts/actuarial_enrichment_pass.py`) | Match 9-dim state key to actuarial cache, inject win_rate/expected_move/efficiency | Package JSONs, actuarial cache parquet | Actuarial fields in package JSONs | Non-critical; warns if <80% fill | LIVE |
| 7.5 | Phantom Scoring Engine (`scripts/phantom_engine.py`) | Historical edge scoring from Phantom DB | `options_intelligence_{run_id}.csv`, PHANTOM DB | `options_intelligence_phantom_{run_id}.csv` | Non-critical, 1200s timeout; fail-open | LIVE |
| 8c | Core Intel Exporter (`scripts/core_intel_exporter.py`) | Export merged intelligence package | vanguard_signals.csv, options_intelligence CSV | Core intel artifacts | Non-critical | LIVE |
| 8.6 | Trigger Layer - packages (`trigger_layer.py` v2.1, `patch_run_packages`) | Inject trigger analysis into package JSONs; sets `eligible_for_trade` flag | Package JSONs, vanguard_signals_enriched | Updated package JSONs with trigger_codes, trigger_score, go_eligible | Non-critical; EDE falls back if absent | LIVE |
| 8d | SuperBrain Passthrough (`run_superbrain_passthrough`, line 2351) | Copy OI → superbrain_enriched; map options_verdict → sb_final_verdict; insert missing spread cols | OI CSV (phantom preferred) | `superbrain_enriched_{run_id}.csv` | Non-critical; EIL skipped if sb_final_verdict missing | LIVE (passthrough only; scoring DEPRECATED 2026-04-28) |
| 8b-stub | Catastrophe Gate (`catastrophe_gate.py`) | **NO-OP stub** since Sprint 2 | None | Returns True immediately | None — removed from decision chain | DEAD (no-op) |
| 8e | Wall Break Scorer (`wall_break_scorer.py` v1.0) | Five-factor wall break score (vanna, wall weakness, flip clearance, vol loading, momentum) | superbrain_enriched, options_intelligence | `wall_break_scores_{run_id}.csv` | Grades: IMMINENT≥75 / PROBABLE≥55 / POSSIBLE≥35 / UNLIKELY | LIVE |
| ACT-SEQ | Pre-EIL Actuarial Injection (inline orchestrator ~line 4034) | Patch actuarial fields from package JSONs into superbrain_enriched BEFORE EIL subprocess | Package JSONs, superbrain_enriched | Updated superbrain_enriched with win_rate_10d etc.; stamps `actuarial_loaded_pre_eil=True` | Soft gate: logs CRITICAL if fill_rate < 80%; manifest set to ACTUARIAL_DEGRADED | LIVE |
| 9 | EIL (`execution_intelligence_runner.py` v4.1) | 5 microstructure strategies + PSE sizing; EOD_SYNTHETIC path off-hours | superbrain_enriched | `eil_enriched_{run_id}.csv`, `execution_v3_5_{run_id}.csv` | eil_v3_verdict: EXECUTE / ARMED / WATCHLIST / BLOCKED | LIVE |
| 10a | GARCH Runner (`garch_runner.py`) | HAR-RV / GARCH forward variance for each ticker | superbrain_enriched, Polygon API | `garch_forecasts_{run_id}.csv` | Non-critical | LIVE |
| 10b | GARCH Merge (`merge_garch_into_enriched`) | Join l3_ fields into superbrain_enriched AND eil_enriched AND execution CSV | garch_forecasts, superbrain+eil CSVs | Updated CSVs with l3_forward_realised_vol, l3_expected_move_*, l3_iv_tailwind_score | Non-critical | LIVE |
| 8.6b | Trigger Layer - EIL CSV (`trigger_layer.enrich_csv`) | Inject vanguard trigger cols into eil_enriched, then run trigger analysis | eil_enriched, vanguard_signals_enriched | Updated eil_enriched with trigger_codes, trigger_score, go_eligible | Non-critical; warns if zero triggers after injection | LIVE |
| HCG | Handoff Conflict Guard (`enforce_handoff_conflict_guard`) | Validate inter-artifact coherence before export | eil_enriched | Conflict report | **HARD ABORT** of evening workflow if fails | LIVE |
| 9D | McMillan Advisory Layer (`mcmillan_advisory_layer.py`) | Enrich with IV/GEX entry quality, move-vs-theta, crowd arrival, gamma island | eil_enriched | Updated eil_enriched + execution CSV; advisory only | Non-critical | LIVE |
| 9.5 | Execution Decision Engine (`execution_decision_engine.py`) | **COMMENTED OUT** — superseded by PSE inside EIL v4.1 | N/A | N/A | N/A | DEAD |
| 9B | Enhancement Layer (`enhancement_integration.py`) | **COMMENTED OUT** — Kelly/Signal Funnel/RCS | N/A | N/A | N/A | DEAD |
| 9C | Trade Book Builder (`trade_book_builder.py`) | **COMMENTED OUT** — depends on Phase 9B output | N/A | N/A | N/A | DEAD |
| CT-post | Catalyst Truth Engine (post_eil) | Third pass catalyst enrichment | eil_enriched | Updated artifacts | Non-critical | LIVE |
| 10 | EOD Candidate Engine (`eod_candidate_engine.py` v1.3) | Build morning manifest from full EIL+WBS+discovery | eil_enriched, WBS CSV, discovery CSV, vanguard CSV | `morning_candidates_{run_id}.csv` | Tier A/B/C/WATCH classification; SCS scoring | Non-critical (archive runs regardless) | LIVE |

---

## 4. Named-Capability Catalogue

| Capability | Status | Location | Notes |
|-----------|--------|----------|-------|
| Discovery layers (Wyckoff/Crabel/Tier 0-3) | LIVE | `avshunter_discovery_ULTIMATE.py` | swing_fusion optional; falls back to WyckoffEngine only |
| Vanguard actuarial | LIVE | `vanguard/` (separate dir) | 9-dim state key matching; actuarial_database_v6.parquet |
| Options Intelligence | LIVE | `scripts/avshunter_options_intelligence.py` v1.1 | Root `avshunter_options_intelligence.py` is a compatibility shim |
| SuperBrain (scoring engine) | DEPRECATED | `scripts/avshunter_superbrain_layer.py` v2.3.0 | Deprecated 2026-04-28; only passthrough remains active |
| SuperBrain (passthrough) | LIVE | `run_superbrain_passthrough()` in orchestrator | Copies OI → superbrain_enriched; maps options_verdict |
| Wall Break Scorer (WBS) | LIVE | `wall_break_scorer.py` v1.0 | wbs_score 0-100, IMMINENT/PROBABLE/POSSIBLE/UNLIKELY grades |
| Execution Intelligence Layer (EIL) | LIVE | `execution_intelligence_runner.py` v4.1 | 5 strategies: liquidity, IV distortion, GEX flip, OBI, POC timing |
| Exit Discipline Engine (Sprint 1) | LIVE | `avshunter_exit_engine.py` | Wired in `morning_thesis_validator.py` at lines 2943-2952; output: `morning_exit_signals.csv` |
| Trigger Layer | LIVE | `trigger_layer.py` v2.1 | 4 triggers: VOL_COMPRESSION, VWAP_RECLAIM, RANGE_BREAK, TRAP; runs twice (Phase 8.6 + 8.6b) |
| GARCH / HAR-RV | LIVE | `garch_runner.py` + `layer3_forward_variance.py` | HAR-RV method; Polygon price history fetch |
| Transition Matrix | LIVE | `scripts/build_phase_transition_matrix.py` | Reads actuarial DB; writes phase-to-phase probabilities |
| PHANTOM | LIVE | `scripts/phantom_engine.py` + `scripts/phantom_database.py` | 1200s timeout; fail-open; prefers phantom OI CSV over original |
| Kelly Sizer | LIVE (file) / RETIRED (authority) | `kelly_sizer.py` | Half-Kelly fraction=0.5; PSE-01-04: pse_final_size always 0.0 in production |
| PSE (Position Sizing Engine) | RETIRED | Inside `execution_intelligence_runner.py` v4.1 | PSE-01: "PSE is RETIRED from production authority"; pse_final_size=0.0 |
| Convexity Strike Map (CSM) | NOT-FOUND | N/A | Sprint 2 — not yet implemented; only referenced in CLAUDE.md |
| GEX proxy | LIVE | `mcmillan_advisory_layer.py`, options_intelligence | gamma_island_on_path, gamma_island_level, iv_gex_entry_quality |
| McMillan Advisory Layer | LIVE | `mcmillan_advisory_layer.py` | Phase 9D; IV/GEX, move-vs-theta, crowd arrival, gamma island |
| Catalyst Truth Engine | LIVE | `catalyst_truth_engine.py` v1.1 | Runs 3× per evening run (pre_options, post_options, post_eil) |
| Handoff Guard | LIVE | `contracts/handoff_contract.py`, `handoff_contract_audit.py` | Truth packet validation; sovereign gates |
| Morning manifest | LIVE | `eod_candidate_engine.py` → `morning_candidates_{run_id}.csv` | 300+ column schema; >1,000 candidates per run (1,082 on 2026-06-24) |
| FRED macro monitor | LIVE (via bond_macro) | `bond_macro_intelligence.py` | yield_curve from FRED; curve_state, spread_bps |
| Sector mapping | LIVE | `scripts/sector_alignment.py` | TAILWIND/HEADWIND/NEUTRAL per sector; REQUIRED for live capital |
| LSS/Pre-Crowd Signal Engine | PARTIAL | `convergence_engine.py` | ConvergenceResult computed but Enhancement Layer (Phase 9B) commented out; EIL uses it internally |
| SEC EDGAR activist monitor | LIVE | `sec_activist_monitor.py`, `sec_form4_monitor.py` | Form 4 signals in `dropbox/macro/sec_form4_signals.json` |
| Options-skew monitor | LIVE | `morning_gate.py` AG-03 | Skew chain fetch; CALL_SKEW_HIGH / PUT_SKEW_HIGH classification |
| Catastrophe Gate | DEAD | `catastrophe_gate.py` | `run_catastrophe_gate()` is a no-op stub since Sprint 2; shadow-mode CSV ct_enriched no longer written |
| Execution Decision Engine (EDE) | DEAD | `execution_decision_engine.py` | Commented out at orchestrator ~line 4320; superseded by PSE inside EIL v4.1 |
| Enhancement Layer (Phase 9B) | DEAD | `enhancement_integration.py` | Commented out at orchestrator ~line 4392; "V5 Colab decommissioned May 2026" |
| Trade Book Builder (Phase 9C) | DEAD | `trade_book_builder.py` | Commented out at orchestrator ~line 4432; depends on Phase 9B |
| ML Confidence Engine | PARTIAL | `ml_confidence_engine.py`, `confirmation_ingester.py` | Sprint 4; paused pending 30+ clean eligible trades; ml_eligible column in journal schema |
| VANGUARD (actuarial DB) | LIVE | `C:/Users/ACKVerissimo/vanguard/` | actuarial_database_v6.parquet, actuarial_cache.parquet |
| Monetisation Policy | LIVE | `avshunter_monetisation_policy.py` | Advisory policy framework; DecisionStates: GO/GO_SMALL/GO_LATE/WAIT/BLOCK_* |
| Macro Quant Packet | LIVE | `scripts/macro_quant_packet.py` | Reads macro JSON; computes macro_regime_label, freshness_status, data_quality |
| Regime Screener | LIVE | `avshunter_regime_screener.py` | Phase 4.7b; mean-reversion, vol-expansion, structural-breakout signal types |
| Morning Gate | LIVE | `morning_gate.py` v1.2 | 5 checks; GO/FLAG/BLOCK verdicts; 147 GO on 2026-06-24 out of 1,082 candidates |
| Execution Gate | LIVE | `execution_gate.py` v1.1 | spread ≤8%, delta 0.30-0.60, IV ≤60%, runway ≥1.5% |
| Trap-to-Launch Engine (TLE) | LIVE | `avshunter_trap_engine.py` | Sprint 3; Phase 5.5; writes tle_ fields to package JSONs; non-critical |
| Asymmetry Gate Swing | LIVE | `asymmetry_gate_swing.py` | Imported in discovery for entry/stop/target geometry |
| Atheoretic Signals | LIVE | `atheoretic_signals.py` | Used in enhancement pipeline |
| Bond Macro Intelligence | LIVE | `bond_macro_intelligence.py` | Writes `bond_macro_state.json` to dropbox; FRED + Polygon data sources |
| VIX Governor | LIVE | `vix_governor.py` | VIX-based regime adjustment |
| Dropoff Audit | LIVE | `dropoff_audit.py` | Checkpoints at phase0, post_package_build, post_vanguard, post_options |
| UAT Audit Report | LIVE | `uat_audit_report.py` | Written at end of each run |
| Weekly Intelligence Report | LIVE (Sundays) | `weekly_intelligence_report.py` | Stage 10; Sunday evenings only |
| Outcome Capture | LIVE | `outcome_capture.py` | Stage 9; auto-detect exits (expiry, time stop, 80% loss) |

---

## 5. Data Lineage

See companion file: `PIPELINE_ARTIFACT_LINEAGE.md`

---

## 6. Trade-Eligibility & Exit Logic

### Evening → Morning Candidate Gate Chain

```
DISCOVERY (avshunter_discovery_ULTIMATE.py)
  min_price=$5 · max_price=$500 · min_avg_vol20=500K · min_adv_dollars=$2.5M
  min_atr_dollars=$0.40 · min_atr_pct=1.0%
  Tier floors: Tier1≥50 · Tier2≥35 · Tier3≥25 (RISK_OFF Tier1 floor=72)
  Early (Tier0): compression 0.45-0.85 · days_in_range 3-15 · phase≥35
  VMS score injection (scanner_context)
  Swing fusion: direction + intent from WyckoffEngine / swing_fusion
        ↓
VANGUARD (actuarial + structure scoring)
  9-dim state key match: vol_regime|trend_direction|structure_quality|
    wyckoff_phase_bucket|trend_maturity|iv_regime|phase_v2|momentum_bucket|location_bucket
  Actuarial: win_rate_5/10/20d · expected_move · efficiency · penalty_multiplier
        ↓
OPTIONS INTELLIGENCE (scripts/avshunter_options_intelligence.py)
  DTE: 1-45d (medium_term preset) · Delta: 0.35-0.55 target (relaxed to ±0.15)
  Liquidity: max_spread 60% · min OI 200 · min_bid $0.25
  BLOCK gates: BLOCK_THETA >85% theta drag · BLOCK_NO_CONTRACT (relaxed)
  STAND_DOWN: negative payoff path (mark=0)
  Options verdict: EXECUTE / ARMED / STAND_DOWN
        ↓
ACTUARIAL ENRICHMENT (Phase 8.5 + pre-EIL injection)
  Exact match preferred; fallback match; no_match → DATA_WEAK path
  EIL reads: win_rate_10d · expected_move_10d · efficiency_10d
  Soft gate: CRITICAL log if fill_rate < 80%
        ↓
TRIGGER LAYER (Phase 8.6 + 8.6b)
  VOL_COMPRESSION: crabel_state ∈ {COILING,CRABEL_READY,NR7} · compression<0.45 · ATR_pct<30
  VWAP_RECLAIM: event detection · volume_ratio>1.1
  RANGE_BREAK_EARLY: ADX 18-28 · phase ∈ {C,D}
  RANGE_BREAK: ADX>25 · ema_stack=ALIGNED · phase ∈ {MARKUP,DISTRIBUTION}
  TRAP: PCR contradiction + structure failure (pcr_signal guard: only 34% populated)
  GO_ELIGIBLE_PRIMARIES: {VOL_COMPRESSION, RANGE_BREAK_EARLY, RANGE_BREAK, TRAP}
  eligible_for_trade=False if trigger_count=0
        ↓
EIL (execution_intelligence_runner.py v4.1)
  S1 Liquidity: ADX + ATR-pct + avg_volume
  S2 IV Distortion: IVP + iv_rank
  S3 GEX Flip: efficiency_10d + win_rate_10d
  S4 OBI: spread_pct + trend_direction + wyckoff
  S5 POC Timing: poc_price or Wyckoff-derived
  Convergence: ≥2/5 strategies required
  eil_v3_verdict: EXECUTE / ARMED / WATCHLIST / BLOCKED
  PSE: pse_final_size ALWAYS 0.0 (retired)
        ↓
EOD CANDIDATE ENGINE (eod_candidate_engine.py v1.3)
  Tier A: OIS≥35 · RR≥1.5 · WBS PROBABLE · conv_score≥3
  Tier B: OIS≥25 · RR≥1.0 · WBS POSSIBLE · conv_score≥2
  Tier C: OIS≥15 · RR>0
  WATCH: below quality floor
  Output: morning_candidates_{run_id}.csv
```

### Morning Gate Chain (morning_gate.py v1.2)

```
morning_candidates_{run_id}.csv (1,082 candidates on 2026-06-24)
  ↓
CHECK 1 (HARD BLOCK): Invalidation intact?
  Fetch live price (Polygon) · compare to invalidation_level
  FAIL → BLOCK, verdict="BLOCK", no trade
  PASS → continue
        ↓
CHECK 2 (FLAG): Macro regime unchanged?
  Compare eod macro_regime vs current macro_intelligence_latest.json
  FAIL → FLAG, regime_changed=True
        ↓
CHECK 3 (FLAG): Contract liquid?
  Fetch live bid/ask (MarketData.app) · spread threshold 25% default
  FAIL → FLAG, contract repair required at open
        ↓
CHECK 4 (FLAG): Bond macro clear?
  Read bond_macro_state.json · check trade_go and bond_macro_flag
  bond_macro_max_age: 26h
        ↓
CHECK 5 (FLAG): Layer 3 model risk clean?
  l3 checks: VOL_HARDCAP>2.50 / LOW_CONF_HIGH_VOL / THIN_HISTORY / IV_TAILWIND_EXTREME
  FAIL → FLAG, model risk review
        ↓
verdict field: GO (all pass) / BLOCK (CHECK 1 fail) / FLAG (any CHECK 2-5 fail)
Output: morning_validated_trades_{run_id}.csv
        ↓
EXECUTION GATE (execution_gate.py v1.1)
  spread ≤8% (SPREAD_FULL=0.08, SPREAD_MAX=0.15)
  delta 0.30–0.60 (DELTA_SOFT_MIN/MAX); hard limits 0.20–0.85
  IV ≤60% (IV_ELEVATED); ≤100% (IV_EXTREME)
  runway ≥1.5% (MIN_RUNWAY_PCT)
        ↓
morning_execution_permission: GO / FLAG / BLOCK
final verdict: GO → READY_EXECUTE → LIVE_VALIDATED → MANUAL_ENTRY_ALLOWED
```

### Exit Engine Chain (avshunter_exit_engine.py — Sprint 1)

```
Run: morning_validated_trades.csv + trade_journal.db (open positions)
  ↓
TRIGGER 1 (highest): Time Stop
  DTE_remaining ≤ 5 → TAKE_FULL
  days_held > DTE_at_entry × 0.75 → TAKE_PARTIAL minimum
        ↓
TRIGGER 2: Profit Capture
  current_premium ≥ entry_premium × 2.0 (100% gain) → TAKE_PARTIAL (50% off)
  current_premium ≥ entry_premium × 3.5 (150% gain) → TAKE_FULL
  current_premium ≥ entry_premium × 1.5 AND days_held > 10 → TAKE_PARTIAL
        ↓
TRIGGER 3: Thesis Integrity
  wyckoff_phase changed → TAKE_FULL
  control_state changed to ADVERSE → TAKE_FULL
  morning_gate verdict = BLOCKED or WAIT → TAKE_FULL
        ↓
TRIGGER 4: IV Crush
  IVP > 70 AND dte_remaining ≤ 10 → TAKE_FULL
  iv_hv_ratio > 1.5 AND days_held > 5 → TAKE_PARTIAL
        ↓
TRIGGER 5: Wall Dynamics
  call_wall migrated BELOW price (CALL pos) → EMERGENCY_EXIT
  put_wall migrated ABOVE price (PUT pos) → EMERGENCY_EXIT
        ↓
Verdicts: HOLD / TAKE_PARTIAL / TAKE_FULL / TRAIL / EMERGENCY_EXIT / DATA_UNAVAILABLE
Output: data/output/runs/{run_id}/morning_exit_signals.csv
```

**Live example (run 20260624_052030):** 1 open position (EMBJ, Trade ID 19, PUT) → HOLD verdict (gain=-0.3%, DTE remaining=17).

---

## 7. External Integrations & Key Config

### API Keys
All stored in `.env` at repo root. Loaded via dotenv in each module; child processes load `.env` directly (parent env vars not reliably inherited on Windows).

| Key | Variable | Used by |
|-----|----------|---------|
| Polygon | `POLYGON_API_KEY` | Discovery (price bars), GARCH (history), morning gate (live prices), options_intelligence (chain) |
| MarketData.app | `MARKETDATA_API_KEY` | Options live quotes, options chain enrichment, morning gate (contract bid/ask) |
| Anthropic | `ANTHROPIC_API_KEY` | Claude API for macro enrichment (GPT delta); model: `claude-sonnet-4-20250514` (`config/settings.json`) |

### Key Thresholds (verified from source)

| Parameter | Value | Source |
|-----------|-------|--------|
| Account size | $50,000 | `OrchestratorConfig.ACCOUNT_SIZE` line 305 |
| Max positions | 5 | `OrchestratorConfig.MAX_POSITIONS` |
| Max probe positions | 3 | `OrchestratorConfig.MAX_PROBE_POS` |
| Universe target size | 6,500 | `evening_workflow()` default |
| Min universe gate | 1,000 | `evening_workflow()` default |
| Discovery min price | $5.00 | `UltimateConfig.min_price` |
| Discovery max price | $500.00 | `UltimateConfig.max_price` |
| Discovery min avg vol | 500K | `UltimateConfig.min_avg_vol20` |
| Discovery Tier 1 floor | 50 (RISK_OFF: 72) | `UltimateConfig.tier1_min` |
| Options DTE | 1-45d | `config/options_settings.json` medium_term preset |
| Options target delta | 0.35-0.55 (relaxed ±0.15) | scripts/avshunter_options_intelligence.py v1.1 FIX-NO-CONTRACT-01 |
| Options max spread | 60% | `config/options_settings.json liquidity_filters` |
| Options min OI | 200 | `config/options_settings.json` |
| Execution spread cap | 8% (SPREAD_FULL), 15% (SPREAD_MAX) | `execution_gate.py ExecutionGateConfig` |
| Execution delta | 0.30-0.60 (soft), 0.20-0.85 (hard) | `execution_gate.py` |
| Kelly fraction | 0.5 (Half-Kelly) | `kelly_sizer.py KELLY_FRACTION` |
| PSE final size | 0.0 (always, retired) | `execution_intelligence_runner.py` PSE-01 |
| Wyckoff min score | 40 | `config/mastermind_config.json` |
| Crabel compression max | 0.85 | `config/mastermind_config.json` |
| GARCH history bars | 252 | `garch_runner.py PRICE_BARS` |
| Macro freshness threshold | 14h | `morning_gate.py MACRO_MAX_AGE_H` |
| Bond macro freshness | 26h | `morning_gate.py BOND_MACRO_MAX_AGE_H` |
| Morning spread threshold | 25% | `morning_gate.py DEFAULT_SPREAD_THRESHOLD` |
| Actuarial fill rate gate | 80% | orchestrator ~line 4161; logs CRITICAL below |
| GO count regression limit | 10% | CLAUDE.md (not hardcoded — manual check) |

### Macro State (as of 2026-06-23)
- `regime_state: TRANSITIONAL_BEARISH`
- `macro_conviction: 0.52`
- `macro_filter: NO_GO` (Fung-Hsieh accuracy 0.444 → 0.7x size modifier active)
- All three horizons: NEUTRAL bias (bullish_prob 52.4-53.0%)
- `size_multiplier: 0.52`
- VIX: 19.49, VIX contango

---

## 8. Findings & Observations

### F-01: Phase Numbering Inconsistency
The orchestrator phase labels and CLAUDE.md phase sequence disagree. The orchestrator calls Discovery "PHASE 1", but CLAUDE.md calls it "Phase 3". Options Intelligence is labelled "PHASE 8b" in orchestrator but "Phase 7" in CLAUDE.md. The actual execution order is consistent; only the labels differ. Risk: operator navigation confusion during debugging.

### F-02: Three Dead Execution Paths (Commented Out)
Phase 9.5 (EDE), Phase 9B (Enhancement Layer), and Phase 9C (Trade Book Builder) are fully commented out in `evening_workflow()` at lines ~4302-4480. The comments state "V5 Colab decommissioned (May 2026)" and "PSE inside EIL runner is the replacement." These dead code blocks span ~180 lines and contain partially functional scaffolding. Risk: future reactivation of one without the other (9C requires 9B output).

### F-03: SuperBrain Scoring Deprecated (Passthrough Only)
`run_superbrain_layer()` at line 2230 is a single-line delegate to `run_superbrain_passthrough()`. The full scripts/avshunter_superbrain_layer.py (2,000+ lines, v2.3.0 with 5 layers) is never called in the evening workflow. sb_final_verdict is simply copied from options_verdict. Fields like sb_conv_score, sb_campaign (STAGED), sb_warnings_count are populated via the passthrough copy but no SuperBrain scoring logic fires. The morning_candidates CSV shows these fields populated with values from the OI → passthrough path.

### F-04: PSE Always Returns 0.0
`execution_intelligence_runner.py` v4.1 PSE-01 states "PSE is RETIRED from production authority." `pse_final_size` is always 0.0. `candidate_size` is always 0.0. `sizing_policy` is "ADVISORY_ONLY". Manual sizing is required for every trade. No automated capital constraint is active.

### F-05: WBS Scores are Uniformly 0.0 in Live Data
The morning_candidates CSV from run 20260624_052030 shows `wbs_score=0.0` and `wbs_grade=NONE` for all reviewed rows. This means the Wall Break Scorer is either not populating scores or the EIL/EOD candidate engine is not finding the wall_break_scores CSV. UNVERIFIED: whether this is expected (no PROBABLE/IMMINENT signals) or a wiring gap.

### F-06: pcr_signal Field is ~34% Populated
Confirmed in `trigger_layer.py` v2.0 Fix 10: "pcr_signal absent guard added. pcr only populated for 34% of universe." The TRAP trigger requires PCR contradiction. This means TRAP trigger can fire on at most ~34% of signals, and PCR-absent tickers always fail the contradiction check. IMPACT: GO_ELIGIBLE count underestimates signals that would qualify if PCR were available.

### F-07: Catastrophe Gate is a No-Op
`catastrophe_gate.py` (v1.0, shadow mode, builds ct_enriched CSV) is registered in check_scripts as optional, but `run_catastrophe_gate()` at line 2495-2505 now returns True immediately with a log message "removed Sprint 2 (was shadow mode, no contribution)." The ct_enriched CSV and ct_summary JSON are no longer written.

### F-08: Multiple Legacy "DNU" Files on Disk
Several files with "dnu" (do-not-use) or "old" suffixes exist in the vanguard directory: `build_phase_transition_matrixanother dnu2005.py`, `build_phase_transition_matrixdnumalomo2005.py`, `kelly_sizeranotherdnu2005.py`, `kelly_sizerdnu2009.py`, `transition_matrix_consumeranotherdnu2005.py`. These are inert but present risk if accidentally imported.

### F-09: Orphaned Backup Files in scripts/
The scripts/ directory contains numerous `.bak_*` files: `avshunter_options_intelligence.py.bak_e2e_options_lab_sync_20260522_034241`, `phantom_engine.py.bak_phantom_20260526_074026`, etc. These are not executed but add maintenance overhead and potential confusion.

### F-10: EIL-GARCH Sequencing Issue (Self-Noted)
The orchestrator notes at line 4196: "Must run AFTER EIL so eil_enriched_{run_id}.csv exists for the merge." GARCH runs at Phase 10a AFTER EIL (Phase 9), which is correct. However, the comment at line 2793 (Phase 10b logic) warns: "Ensure Phase 10b runs AFTER Phase 9 (EIL) for full GARCH enrichment." This is correctly sequenced in the current workflow but was historically a bug source.

### F-11: macro_data_quality=PARTIAL in Live Run
The morning_candidates CSV shows `macro_data_quality=PARTIAL` for all candidates. The macro JSON notes: `MACRO_MISSING_REVIEW_REQUIRED|MACRO_DATA_MISSING|LOW_MACRO_CONFIDENCE` in macro_conflict_flags. The macro_quant_packet shows `macro_data_quality=PARTIAL`. This degrades the manifest confidence but does not block execution.

### F-12: Equity Drawer Active = Strong Confirmation Required
All signals in the 20260624 run show `capital_authorization_state=EOD_CANDIDATE_ONLY` and `execution_authority_reason=EQUITY_DRAWER_ACTIVE_REQUIRES_STRONG_CONFIRMATION`. This is the correct behaviour under `TRANSITIONAL_BEARISH` regime with Fung-Hsieh NO-GO active. No signals achieved automatic FULL_EXECUTE authorization.

### F-13: Options Intelligence Root File is a Shim
`avshunter_options_intelligence.py` in the root is NOT the production module — it is a shim that calls `runpy.run_path(scripts/avshunter_options_intelligence.py)`. The orchestrator path `cfg.OPTIONS_INTEL` must be verified to point to `scripts/` not root. UNVERIFIED: exact path in OrchestratorConfig.

### F-14: VANGUARD_DIR is Outside Repository
`VANGUARD_DIR = Path(r"C:\Users\ACKVerissimo\vanguard")` — all actuarial builder, DB, and cache scripts are outside the AVSHUNTER-Intelligence repo directory. This is by design but means git does not track the actuarial database or cache.

### F-15: Morning Exit Signals Show No Exits in Latest Run
The `morning_exit_signals.csv` from run 20260624_052030 shows 1 position (EMBJ, Trade ID 19, PUT, 6 days held, 17 DTE remaining, gain=-0.3%) with HOLD verdict. The exit engine is functional and wired.

---

## 9. Coverage & Confidence

### Coverage
- **Orchestrator phase chain**: 95% — read lines 1515-5090 covering full evening_workflow and premarket_workflow
- **Core phase modules**: 90% — read opening 80-150 lines of all named modules; full reads of discovery, options intelligence, superbrain, trigger layer, catastrophe gate, WBS, GARCH, EIL, EOD candidate engine, morning gate, execution gate, exit engine, trap engine
- **Supporting modules**: 70% — read opening sections of convergence_engine, monetisation_policy, catalyst_truth, handoff_contract, lab_control, kelly_sizer, bond_macro_intelligence
- **Config files**: 100% — all 5 JSON configs read in full
- **Data artifacts**: 80% — latest run directory fully mapped; morning_candidates and morning_validated_trades from run 20260624_052030 verified; macro_intelligence and bond_macro_state JSON read; morning_exit_signals.csv verified
- **Scripts/ directory**: 60% — module names catalogued; production OI and superbrain read in detail; phantom, actuarial, vanguard scripts opened
- **Bridge/ directory**: 60% — file names read; tastytrade_client confirmed as non-trading placeholder
- **Pipeline_interpreter/**: 50% — file names catalogued; individual files not read

### Items Marked UNVERIFIED
- Whether WBS 0.0 scores are correct or indicate a wiring gap (F-05)
- Exact `cfg.OPTIONS_INTEL` path in OrchestratorConfig (F-13 — shim vs scripts/)
- Whether `enhancement_integration.py` is actually on disk (orchestrator comments say "CONFIRM")
- PHANTOM DB coverage percentage and which tickers have historical data
- Exact state of `confirmation_ingester.py` gate logic (Sprint 4 partly built)
- Whether `avshunter_universe_scanner.py` in scripts/ is the active VMS scanner used at Phase 0

### Confidence
HIGH for phase chain and phase dependencies. MEDIUM for module-level field contract completeness (many modules have 200-500+ output fields; only key fields were traced). LOW for dead-code completeness (some commented blocks may reference modules that no longer exist or have been renamed).
