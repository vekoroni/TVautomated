# AVSHUNTER Pipeline — End-to-End Map (Macro → Intelligence Lab)

**Date:** 2026-08-29 | **Pack ID:** AVS-MAP-001-EXEC-CC v2 | **Status:** Read-only investigation, complete
**Ground truth used:** live code in the working tree as of 2026-08-29, cross-checked against the same-day full pipeline run `data/output/runs/20260829_100803/` and (for morning/execution-gate stages, which today's run had not yet reached) the most recent completed morning run `data/output/runs/20260828_094349/`.

## How this pack was built

Four subagents investigated in parallel, each covering a phase range plus one phase either side for interface verification, acting simultaneously as Business Analyst / QA / Developer per the brief's investigation lens. Every finding below is tagged with its verification method. This document stitches their Stage Cards into actual execution order — which, as documented below, is **not** the same as the pipeline's own phase numbering.

- **Agent 1** — Preflight → Macro Normalisation → Actuarial Cache/Query → Discovery → External Intel → Package Build/Backfill
- **Agent 2** — Vanguard → Options Intelligence → EV3 Shadow → Actuarial Enrichment → Phantom → Trigger Layer → SuperBrain passthrough → Catastrophe Gate → Wall Break Scorer
- **Agent 3** — EIL boundary → GARCH → Trigger Layer (post-EIL) → Catalyst Truth → McMillan → EOD Candidate Engine → Pipeline Integrity → Diagnostics → morning_gate.py (all checks) → morning_handoff_finalizer → execution_gate
- **Agent 4** — Governed Book construction (`contracts/lab_control.py`) → Intelligence Lab UI consumption

## Top-level finding: phase *numbers* in this codebase do not track execution *order*

This is a standing finding, not an artefact of this pack's organisation. Directly observed:
- `macro_horizon_router.py` is labelled "PHASE 1B: HORIZON ROUTER" in its own log line but is actually invoked after Phase 8a (Options Intelligence) in `intelligent_orchestrator.py`.
- The Trigger Layer's second pass, labelled "Phase 8.6b", is documented in-code to run *after* Phase 9 (EIL) and Phase 10a/10b (GARCH) — "POSITION FIX: Phase 8.6 now runs AFTER EIL (Phase 9) so eil_enriched CSV exists when enrich_csv() is called" (`intelligent_orchestrator.py:4345-4346`).
- "Phase 8b" is used as a self-label by *both* Options Intelligence and the (no-op) Catastrophe Gate.
- `docs/pipeline_map/06_MORNING.md` (2026-08-20) describes `morning_gate.py` as having 5 checks; the current code (modified today) has 8.
- The orchestrator's own code comments use "Phase 11" to mean Execution Gate, which the original brief's phase range table assigned to "Diagnostics/Archive."

**Impact:** anyone — human or another audit pass — reasoning about this pipeline from phase numbers alone will misorder stages. This map presents stages in actually-observed execution order, with each stage's self-declared phase label noted separately.

---

## Confirmed actual execution order

```mermaid
sequenceDiagram
    participant P0 as Preflight
    participant MN as Macro Normalisation
    participant AC as Actuarial Cache Build
    participant DISC as Discovery
    participant EI as External Intel Lane
    participant PKG as Package Build/Backfill
    participant VG as Vanguard (Layer1/2)
    participant OI as Options Intelligence
    participant HR as Horizon Router
    participant EV3 as EV3 Governed Shadow
    participant AE as Actuarial Enrichment
    participant PH as Phantom Scoring
    participant TL1 as Trigger Layer (pkg patch)
    participant SB as SuperBrain Passthrough
    participant CG as Catastrophe Gate (no-op)
    participant WBS as Wall Break Scorer
    participant EIL as EIL / PSE (Phase 9)
    participant GARCH as GARCH Runner
    participant TL2 as Trigger Layer (EIL CSV, "8.6b")
    participant CT as Catalyst Truth (post-EIL)
    participant MCM as McMillan Advisory
    participant EOD as EOD Candidate Engine
    participant PI as Pipeline Integrity Report
    participant DIAG as Diagnostics/Archive
    participant MG as morning_gate.py (8 checks)
    participant MHF as morning_handoff_finalizer
    participant EG as execution_gate.py
    participant LAB as Intelligence Lab (Governed Book + UI)

    Note over P0,PKG: Agent 1 scope
    P0->>MN: macro_path (soft-required)
    MN->>DISC: macro_snapshot / regime state
    AC->>DISC: (independent cache build, phase 4.6)
    DISC->>EI: discovery_candidates_ultimate.csv
    EI->>PKG: patched discovery CSV (advisory-only additions)
    PKG->>VG: packages/*.package.json (data_contract flags STALE post-backfill)

    Note over VG,WBS: Agent 2 scope
    VG->>OI: vanguard_signals.csv (state_hash, behaviour_state_hash)
    OI->>HR: options_intelligence.csv
    HR->>EV3: horizon-patched OI csv (governed horizon)
    EV3->>AE: ev3_authority_overlay (ADVISORY ONLY, hardcoded)
    AE->>PH: actuarial-enriched packages -> superbrain_enriched
    PH->>TL1: phantom-enriched OI csv (ADVISORY_PROMOTION)
    TL1->>SB: package.json triggers patched
    SB->>CG: superbrain_enriched.csv (pure passthrough, dead logic)
    CG->>WBS: no-op
    WBS->>EIL: wall_break_scores.csv (IMMINENT/PROBABLE grades)

    Note over EIL,DIAG: Agent 3 scope
    EIL->>GARCH: eil_enriched.csv (pse_final_size = 0.0 always)
    GARCH->>TL2: l3_* fields merged into eil_enriched
    TL2->>CT: trigger_go_eligible materialised flat
    CT->>MCM: catalyst_truth_score (1% real coverage)
    MCM->>EOD: advisory fields only, read-only
    EOD->>PI: morning_candidates.csv (817 rows today)
    PI->>DIAG: manifest_permission=MORNING_VALIDATION_REQUIRED
    DIAG->>MG: [TODAY'S RUN STOPS HERE — morning_gate not yet run]
    MG->>MHF: verdict/morning_execution_route (8 checks, 2 advisory-only)
    MHF->>EG: fail-closed hash reconciliation

    Note over LAB: Agent 4 scope
    EG->>LAB: write_final_opportunity_book (297 fields)
    LAB->>LAB: UI surfaces ~138/297 fields; several read dead legacy keys
```

---

## Stage Cards — actual execution order

### Stage: Preflight
- **Trigger:** `run_preflight_checks()`, `intelligent_orchestrator.py:1139`, first call in evening `main()`.
- **Inputs:** `UNIVERSE_FILE` row count; dependency-script existence; macro JSON required-field check (`risk_on_switch, regime_state, dir_bias, regime_drift_status, conviction_score, macro_conviction, liquidity_status, volatility_mode, vix_contango, report_date, as_of_utc`).
- **Processing summary:** Three gates ANDed. Universe gate (HARD/SOFT/AUTO, default AUTO — hard-fails only below `min_universe`). Macro gate is **soft by default**: `AVSHUNTER_MACRO_CORE_REQUIRED=0` means a missing/invalid macro file degrades to a governed "neutral sidecar" rather than blocking.
- **Outputs:** pass/fail boolean, resolved `macro_path` (or `None`).
- **Confidence/quality fields:** none created; presence-checked only.
- **Gates/thresholds:** `MACRO_STALE_HOURS = 20` — staleness beyond this is a non-blocking warning only.
- **Verification method:** code read + run artefact (today's macro was 2.1h old, well within threshold).
- **Prior claim(s):** MEMORY.md "enrichment graceful degradation" (2026-05-22 macro redesign) — **CONFIRMED**.
- **Efficiency gap:** Low — deliberate, documented design; no evidence of unexpected firing.
- **Downstream consumer:** Macro Normalisation, Discovery.
- **Card confidence:** High. *(Agent 1)*

### Stage: Macro Normalisation (`build_macro_json.py`, `macro_horizon_router.py`, `bond_macro_intelligence.py`, `contracts/bond_macro_contract.py`, `contracts/macro_enrichment_delta.py`)
- **Trigger:** `build_macro_json.py` runs upstream of the orchestrator; `macro_horizon_router.py` and `bond_macro_intelligence.py` run inside it at points that don't match their own phase labels (see top-level finding).
- **Inputs:** ~20 CSV/JSON files under `dropbox/market_data/` (FRED, GEX, VIX engine, liquidity monitor, sector data); `bond_macro_intelligence.py` pulls Treasury auction calendar, FRED yield series, Polygon ZN futures OHLCV, HYG/LQD ratio.
- **Processing summary — critical finding:** `build_macro_json.py` is **not deterministic**. `call_macro_api()` makes a live 3-message call to `anthropic.Anthropic()`, model `claude-sonnet-4-6`, and the LLM's free-text-then-JSON response supplies `regime_state`, `dir_bias`, **`macro_conviction`** (explicitly prompted as "a confidence score 0-100"), and `regime_probability`. Only `vix_regime_score`, `credit_risk_score`, `gex_regime_score`, `net_liquidity_score` are computed deterministically afterward. `bond_macro_intelligence.py` is fully deterministic (baseline 70, bounded deltas for curve state / ZN direction / HYG-LQD credit z-score, clamped 0-100).
- **Outputs:** `macro_snapshot.json`, `macro_quant_packet.json`, `horizon_summary_{run_id}.json`, `bond_macro_state.json`.
- **Confidence/quality fields introduced:** `macro_conviction` (0.5513 today, **LLM output**), `regime_probability`, deterministic overrides (`vix_regime_score` etc.), `bond_macro_score`/`bond_macro_flag`, per-horizon `bullish_prob_pct`/`size_multiplier`.
- **Gates/thresholds:** "macro conviction below full-size threshold" flag exists but exact literal not confirmed in the excerpt read (flagged unverified detail); `CREDIT_WARN_ZSCORE=1.5`/`CREDIT_ALERT_ZSCORE=2.5`.
- **Verification method:** code read + run artefact (`macro_snapshot.json._builder_metadata.model = "claude-sonnet-4-6"`, `built_at: 2026-08-29T08:46:33Z` — confirms today's run used the real API call, not a stub).
- **Prior claim(s):** none of the named prior docs flagged the LLM-in-the-loop mechanism — **new finding**.
- **Perceived efficiency gap — HIGH:** `macro_conviction` is the master confidence figure the entire horizon-routing/sizing cascade is built on, and it is a single subjective LLM judgment with no calibration/backtest evidence found, re-derived from scratch every run. This is the single least-verifiable number sitting at the top of the whole confidence lineage, directly conflicting with the objective's "free of unverified assumptions" bar.
- **Second finding (Medium):** `contracts/bond_macro_contract.py` intentionally nulls `bond_macro_score` and downgrades the flag to `BOND_MACRO_PARTIAL_CONTEXT` when the yield-curve sidecar is stale. Verified today: the sidecar computed a real 55/100 `BOND_MACRO_CAUTION` score with an explicit staleness warning (yield curve 2 sessions old), but `macro_quant_packet.json` shows the score silently nulled — real signal, dropped due to upstream FRED data freshness, not a bug per se.
- **Downstream consumer:** Package Build (embeds macro verbatim into every package); Discovery (state-prior adjustment).
- **Card confidence:** High. *(Agent 1)*

### Stage: Actuarial Cache Build (Phase 4.6, `actuarial_cache_builder.py` in `C:\Users\ACKVerissimo\vanguard`) and Actuarial Query (`vanguard/layer2_statistical/actuarial_query.py`, `state_calculator.py`)
- **Trigger:** Orchestrator Phase 4.6 (`:3887-3960`); note this runs against a **separate directory tree** (`C:\Users\ACKVerissimo\vanguard`, distinct from the repo's own `vanguard/`).
- **Inputs:** canonical `actuarial_database_v7.parquet` — **3,816,857 rows, 67 columns** (confirmed live count via `pyarrow.parquet.ParquetFile.metadata.num_rows`) → aggregated into `actuarial_cache_v7.parquet` (508 state combinations × 45 outcome columns, built 2026-08-29 08:54 UTC).
- **Processing summary:** Multi-tier match ladder — `MATCH_EXACT_DIMS` (9 dims) → `RELAXED` → `ANALOGUE` (min 100 samples) — each tier weighted (`CONFIDENCE_WEIGHTS`: EXACT-HIGH=1.00 down to UNKNOWN=0.30). Never returns `None` (fail-closed default).
- **Outputs:** `pkg["actuarial"]` block per package: `sample_size`, `state_match_quality`, `confidence_weight`, `layer2__probability_verdict/edge`, `actuarial_match_type`, `actuarial_ev_weight`.
- **Confidence/quality fields:** `sample_confidence_bucket`, `confidence_penalty`, `confidence_weight`, `state_match_quality`, `state_match_similarity`, `actuarial_match_type`, `layer2__probability_verdict` (NEGATIVE_EDGE/WEAK_EDGE/MODEST_EDGE/STRONG_EDGE).
- **Gates/thresholds:** cache-level `sample_size < 30` → 54/508 states flagged invalid (matches `actuarial_last_run.json` exactly: `valid_states=454, invalid_states=54`).
- **Verification method:** code read + direct parquet queries + full-population aggregation across 1,528 real packages from today's run.
- **Prior claim(s):** MEMORY.md "Actuarial v6 Registry Fix 2026-06-05" (fingerprint stale since 20 May, fixed for `iv_regime/horizon_bucket/crabel_state`) — **CONFIRMED still holding**: registry `expected_schema_fingerprint` (`f39c12cd6436...`) matches exactly what's stamped into today's live package output, no drift.
- **Perceived efficiency gap — HIGH (population-level, real data):** Across 1,528 packages: `layer2__probability_verdict = NEGATIVE_EDGE` for **944 (61.8%)**, `WEAK_EDGE` 342, `MODEST_EDGE` 98, `STRONG_EDGE` only 98 (6.4%). This is strong direct evidence for why the trade journal produces no trades: the actuarial layer's own edge calculation says most candidates have negative expected edge, well before execution gating. `actuarial_match_type = BROAD_ONLY_MATCH` for 76.6% of packages — only 12.3% get a true EXACT match.
- **Second finding — Medium, verified at scale:** `scripts/actuarial_enrichment_pass.py` merges the fresh lookup **on top of** the existing dict rather than replacing it, so every successfully-enriched package still carries the Stage-5 placeholder's `"deferred": true, "reason": "Awaiting Phase 8.5 actuarial_enrichment_pass"` alongside fully real `sample_size`/`valid`/`enriched_at` values. Confirmed on real package `A.package.json`. No confirmed live consumer trusts `deferred` today, so impact is contained to human/QA trust, not pipeline behaviour — but it is a genuine internal-consistency defect.
- **Downstream consumer:** Vanguard, EV/execution engines.
- **Card confidence:** High. *(Agent 1)*

### Stage: Discovery (`avshunter_discovery_ULTIMATE.py`, `canonical_data/discovery_publisher.py`)
- **Trigger:** Orchestrator "PHASE 1: DISCOVERY" (`:1624-1789`), after Preflight.
- **Inputs:** universe CSV, OHLCV bars, sector map, macro snapshot (`macro_momentum_score` state-prior adjustment).
- **Processing summary:** `wyckoff_score`, `crabel_score` combine into `composite_score = wyckoff*0.6 + crabel*0.4` (Wyckoff-only fallback if no Crabel signal). A separate "early position" path can short-circuit to `tier=0` independent of the score ladder. `apply_state_prior_adjustment()` applies bounded (max +15/-20) empirically-derived adjustments keyed by `(wyckoff_phase_bucket, macro_regime)`, cited as sourced from "3.7M cleaned actuarial observations" (mechanism/bound verified; underlying bucket percentages not independently re-derived).
- **Outputs:** `discovery_candidates_ultimate_{run_id}.csv`, `discovery_candidates_cds3_{run_id}.csv`, `discovery_lifecycle_{run_id}.csv`.
- **Confidence/quality fields:** `wyckoff_score`, `crabel_score`, `composite_score`, `tier`/`tier_label`, `win_probability`, transition-probability fields, `fusion_alignment_score`, `vms_score`.
- **Gates/thresholds:** `tier1_min=50.0, tier2_min=35.0, tier3_min=25.0`, with **regime-adaptive Tier-1 demotion**: RISK_OFF requires ≥72, TRANSITIONAL requires ≥68 to hold Tier 1 (the top-conviction bar rises in cautious regimes).
- **Verification method:** code read + run artefact (`discovery_candidates_ultimate_20260829_100803.csv`, 1,527 rows).
- **Perceived efficiency gap — HIGH:** Real tier distribution: tier 0 (EARLY) 962, tier 2 = 464, tier 3 = 83, **tier 1 = only 18 of 1,527 (1.2%)**. No tier-4/reject rows appear in the CSV (either genuinely none, or filtered before write — not confirmed which). This is a severe, very early funnel narrowing that compounds with the actuarial NEGATIVE_EDGE finding above.
- **Second finding — Low/Medium:** `calculate_win_probability()` is a fixed linear transform (`min(75, max(35, 40 + composite*0.25))`) with no stated empirical derivation, despite a name implying a calibrated statistic — contrast with the explicitly-cited state-prior table beside it.
- **Downstream consumer:** External Intel lane, Package Build.
- **Card confidence:** Medium-High — mechanics directly verified; empirical basis of the state-prior table and win_probability formula not independently re-derivable in scope. *(Agent 1)*

### Stage: External Intel / Macro Enrichment Lane (`scripts/apply_external_intel_review_lane.py`, `contracts/macro_enrichment_delta.py`)
- **Trigger:** `apply_external_intel_review_lane(run_id, macro_path)`, non-critical, after Discovery/macro normalisation.
- **Processing summary:** Strictly additive/advisory. Discovery survivors also in the catalyst calendar or macro exposure index get `external_intel_*` columns stamped on their existing row. Catalyst/macro-only tickers Discovery did not select go to a **separate** review-candidates CSV only — cannot rejoin the core CSV or reach Packages/Vanguard (verified: `core_membership_changed: False`). `validate_macro_enrichment_delta()` enforces a protected-field allowlist so a delta can't override core macro fields.
- **Outputs:** patched `discovery_candidates_ultimate` (in place), `external_intel_review_candidates_{run_id}.csv`, `qa/external_intel_review_lane_{run_id}.json`.
- **Confidence/quality fields:** `external_intel_source_tier`, `external_intel_macro_pressure_label`, `external_intel_macro_confirmation_required`, `external_intel_data_quality`.
- **Gates/thresholds:** none numeric — pure membership/tagging.
- **Verification method:** code read + run artefact (37 rows today: 25 `ALREADY_IN_DISCOVERY`, 12 `ADVISORY_ONLY_NOT_DISCOVERY`).
- **Perceived efficiency gap — Low:** working as designed. One latent, currently-inert gap: `find_macro_enrichment_delta()` picks the newest-mtime matching file with no staleness ceiling; harmless today (only one live file exists) but nothing prevents silent reuse of a stale delta if that changed.
- **Downstream consumer:** Package Build.
- **Card confidence:** High. *(Agent 1)*

### Stage: Package Build / Backfill (`scripts/build_packages_from_discovery.py`, `scripts/backfill_timeseries_into_packages.py`)
- **Trigger:** Orchestrator `run_vanguard_pipeline()`, before Vanguard proper.
- **Processing summary:** `build_package()` assembles one JSON per ticker with `discovery`, `regime_snapshot`, `macro.payload`, `ohlcv_daily`, `actuarial` (deferred placeholder). `enforce_data_contract()` runs the data-contract validator **at build time, before OHLCV backfill** — correctly finds no data yet, sets `data_failure=True`, `dcv_valid=False`. `backfill_timeseries_into_packages.py` then writes real OHLCV into `timeseries.ohlcv_daily` and flips `has_ohlcv_daily=True`, but **never touches** `data_failure`/`dcv_valid`/`dcv_bars`/`dcv_confidence` (confirmed by grep — zero references in the backfill script).
- **Outputs:** `packages/{TICKER}.package.json` × 1,527, `packages/index.json`.
- **Gates/thresholds:** backfill systemic-failure abort at `AVSHUNTER_MAX_BACKFILL_FAILURE_RATIO` (default 5%).
- **Verification method:** code read (both scripts, full) + run artefact at scale (400/1,528 packages sampled directly).
- **Prior claim(s):** code self-documents (2026-08-19, "EV audit Stage 0") that `ev_final`/`ev_status` are always `None` at build time — **CONFIRMED still true**.
- **Perceived efficiency gap — HIGH, verified at scale:** 400/400 sampled packages (100%) have `data_failure: True`, 398/400 `dcv_valid: False`, and **388 of those 400 also contain real, populated OHLCV** (typically 1,260 daily bars). Same bug pattern as the actuarial `deferred` finding above: validation snapshot taken once, never refreshed after later stages populate real data. **Mitigating:** the one confirmed live consumer (`avshunter_superbrain_layer.py`) already defends against this, and Vanguard independently re-derives OHLCV presence via multiple real keys rather than trusting these flags — so the primary trade-generation path is not blocked. But it corrupts the field as a trustworthy audit signal for every package in every run.
- **Downstream consumer:** Vanguard.
- **Card confidence:** High. *(Agent 1)*

---

### Stage: Phase 5→6 interface (Packages → Vanguard) — dedicated check: **MATCH**
Orchestrator hands off via a subprocess call gated on `packages/index.json` existing. Today: `packages_built: 1527, packages_blocked: 0`. `run_vanguard_from_packages.py` declares a fail-closed contract and its OHLCV reader checks multiple real fallback keys (`pkg["ohlcv_daily"]`, `pkg["ohlcv"]`, `pkg["timeseries"]["ohlcv_daily"]`) rather than trusting the (broken) `data_failure`/`dcv_valid` flags — a genuine safety net. `vanguard_run_summary.json` today: `packages_total: 1527, passed: 1482 (97.1%), rejected: 45`, all one clean labelled cause (`DATA_FAILURE_NO_OHLCV`), within the 5% tolerance. *(Agent 1 + Agent 2, cross-confirmed)*

### Stage: Vanguard — Layer 1 (Auction) / Layer 2 (Statistical) (`vanguard/main.py`, `vanguard/core/actuarial_core_v7.py`, `scripts/run_vanguard_from_packages.py`, `scripts/behaviour_state_builder.py`)
- **Trigger:** `run_vanguard_pipeline()` Phase 6, after Package Build.
- **Processing summary:** `AuctionStateSynthesizer` (layer1) → `StateVectorCalculator`/`ActuarialQueryEngine`/`EdgeDetector` (layer2), gated by `OrchestratorAdapter` which fail-closes on missing `regime_snapshot`/OHLCV. **Execution authority is explicitly excluded** — `vanguard/main.py:16-17`: "Vanguard is an intelligence layer only. Execution authority belongs to Options Intelligence → EIL → PSE → MVE." `state_hash` computed from a 9-dim `CORE_HASH_DIMENSIONS` set; a *separate* `behaviour_state_hash` computed from a different 7-dim `BEHAVIOUR_DIMS` set (documented as additive, finer-grained).
- **Outputs:** `vanguard/vanguard_signals.csv` (PASS), `vanguard_rejects.csv`, `vanguard_run_summary.json`.
- **Confidence/quality fields:** `state_hash`, `behaviour_state_hash`, `sample_confidence_bucket` (HIGH_SAMPLE≥100/USABLE_SAMPLE≥50/WEAK_SAMPLE≥30/CONTEXT_ONLY≥10/INSUFFICIENT_SAMPLE<10), `preferred_horizon`, `n_observations`, `win_rate_{5,10,20}d`, `expected_value_{5,10,20}d`, `has_edge`, `edge_direction`.
- **Gates/thresholds:** backfill 5% tolerance (above); actuarial DB filename/schema contract check; per-package fail-closed isolation.
- **Verification method:** code read + run artefact (`vanguard_run_summary.json`).
- **Perceived efficiency gap — Medium:** `vanguard/main.py` explicitly documents that downstream consumers (EIL, MVE, PSE) **must** gate on `sample_confidence_bucket` — "INSUFFICIENT_SAMPLE/CONTEXT_ONLY must never reach execution" — but grep of `execution_intelligence_runner.py`, `trigger_layer.py`, `final_decision_engine.py` finds **zero gating hits**; `eod_candidate_engine.py` only passes it through. Currently moot (nothing reaches capital regardless — see EIL/PSE below), but the documented safeguard won't fire automatically if PSE is reactivated.
- **Downstream consumer:** Options Intelligence.
- **Card confidence:** High. *(Agent 2)*

### Stage: Options Intelligence (`scripts/avshunter_options_intelligence.py`)
- **Trigger:** Immediately after Vanguard, before macro horizon router.
- **Processing summary:** Per-ticker contract selection + OIS composite scoring + verdict derivation. This module received a prior, independent, artefact-verified deep audit (`docs/pipeline_map/03_PHASE_7_OPTIONS.md`, 2026-08-20) covering the `derive_verdict()` gate ladder, spread-gate synthetic-mark asymmetry, and `block_code` dual-meaning issue — **not independently re-derived this pass** (out of this agent's assigned mandate).
- **Outputs:** `options_intelligence_{run_id}.csv`, `vanguard_signals_enriched_{run_id}.csv`, `contract_rejection_log_{run_id}.csv`.
- **Confidence/quality fields:** `options_verdict` (STAND_DOWN/ARMED/EXECUTE), `options_verdict_tier`, `final_route`, `options_research_score`, `contract_score`, `options_score` (OIS).
- **Verification method:** code read (module structure only) + run artefact checked directly by this pass: today — STAND_DOWN 1,102 (83.7%), ARMED 133, EXECUTE 81 (6.2%), same order of magnitude as the prior audit's reference runs (7.8-8.8%).
- **Prior claim(s):** the prior deep audit's specific funnel/gate claims are **carried forward, not re-verified this pass** — flagged explicitly as such rather than re-asserted as current fact.
- **Perceived efficiency gap:** carried forward at **High** per the prior audit (`BLOCK_NO_CONTRACT` largest single attrition point) — not independently re-assessed here.
- **Downstream consumer:** Horizon Router, EV3 shadow, SuperBrain passthrough, Wall Break Scorer, Trigger Layer.
- **Card confidence:** Low-Medium for the deep funnel claims (correctly attributed, not re-verified); High for the interface/schema facts checked directly. *(Agent 2)*

### Stage: Horizon Router patch (mislabelled "Phase 1B", actually runs after Options Intelligence)
Patches governed per-horizon direction/size fields onto the OI CSV, explicitly sequenced before EV3 so "EV3 must evaluate the final governed horizon, never the provisional Options Intelligence horizon." See top-level finding for the phase-numbering issue. *(Agent 1 + Agent 2)*

### Stage: EV-1.5 / EV3 Governed Shadow (`vanguard/ev_engine_v3.py`, `vanguard/ev3_stage0.py`, `scripts/apply_ev3_authority.py`)
- **Trigger:** Immediately after Horizon Router.
- **Processing summary:** `ev_engine_v3.py` compares long CALL/PUT vs. debit spreads via a barrier-crossing probability model (CRR/BSM), producing governed evidence. `apply_ev3_authority.py` overlays this onto the options CSV.
- **Outputs:** `ev3_shadow/ev3_stage1_shadow_results.parquet`, `ev3_authority_overlay.csv`, `ev3_calibration_readiness.json`.
- **Confidence/quality fields:** `ev3_authority_state`, `ev3_monetisation_permission`, `ev3_ev_eligible`, `ev3_authority_active`, `capital_authority_calibrated`.
- **Gates/thresholds:** `authority_active` is a **hardcoded `False`** literal (`apply_ev3_authority.py:153`) — not a computed gate. Separate calibration-readiness gate would additionally require `minimum_matched_outcomes=30` even if authority were re-enabled.
- **Verification method:** code read + run artefact — today: 1,316/1,316 rows `ev3_authority_active=False`; `ev3_calibration_readiness.json`: `status=INSUFFICIENT_OUTCOMES`, `matched_outcome_rows=0`, `journal_outcome_rows=14` (minimum 30).
- **Prior claim(s):** brief's own framing ("verify 'shadow' is actually shadow-only") — **CONFIRMED**, more strongly than naming suggests: the `--enable-authority` CLI flag and `AVSHUNTER_EV3_AUTHORITY_ENABLED` env var are both read but do not reach the `authority_active` assignment — there is no documented way to turn this on today.
- **Perceived efficiency gap — HIGH:** This is the most mature, most carefully engineered scoring layer in the whole signal-engine range (governed barrier-crossing model, explicit calibration contract, per-row audit trail) — fully inert with respect to capital. Its own reactivation condition (≥30 matched outcomes) cannot be met without live trades, which cannot happen without a capital-authority path. **Closed loop**, and this is the same closed loop the PSE finding below describes system-wide.
- **Downstream consumer:** advisory only.
- **Card confidence:** High. *(Agent 2)*

### Stage: Actuarial Enrichment Pass (Phase 8.5)
- **Trigger:** After Options Intelligence, before Phantom.
- **Processing summary:** Patches `pkg["actuarial"]` using a **second, independently-defined** 9-dim state key (`vol_regime, trend_direction, structure_quality, adx_bucket, wyckoff_phase_bucket, macro_regime, trend_maturity, catalyst_proximity, atr_pct_bucket`) — different from Vanguard's own `CORE_HASH_DIMENSIONS`. Re-injected as flat columns into `superbrain_enriched` before EIL (which reads them via `EVEngineV2`, not EV3).
- **Gates/thresholds:** 80% fill-rate soft gate — logs CRITICAL and sets `DEGRADED` on breach, does not abort.
- **Verification method:** code read only (fill-rate not artefact-checked for today's run).
- **Perceived efficiency gap — Medium (new finding):** two independently-defined 9-field actuarial state-key schemes exist for what a reader would assume is "the" actuarial state key, increasing audit surface and making "how confident is the actuarial edge" harder to trace as one lineage.
- **Downstream consumer:** EIL (EVEngineV2).
- **Card confidence:** Medium. *(Agent 2)*

### Stage: Phantom Scoring Engine (Phase 7.5, `scripts/phantom_engine.py`)
- **Trigger:** After Actuarial Enrichment, before Trigger Layer package patching; non-critical, 1,200s timeout with bypass.
- **Processing summary:** Bayesian edge / criticality / gamma-trajectory / info-flow / IV-surface sub-models combine into a Phantom score.
- **Gates/thresholds:** `PHANTOM_AUTHORITY_MODE = "ADVISORY_PROMOTION"` (hardcoded) — same self-documented advisory-until-calibrated pattern as EV3; would flip to `FULL_PROMOTION` only after ≥1 week of live trading data.
- **Verification method:** code read (header/constants only) — not artefact-checked.
- **Perceived efficiency gap — Medium:** a third independently-built "advisory until live outcomes exist" layer, reinforcing that the entire signal-engine stack is architected around a promotion gate none of its components can currently satisfy.
- **Downstream consumer:** SuperBrain passthrough (preferentially reads the phantom-enriched CSV if present).
- **Card confidence:** Low — shallow read, not artefact-verified. *(Agent 2)*

### Stage: Trigger Layer — package JSON patch (Phase 8.6, `trigger_layer.py`)
- **Trigger:** After Phantom/Core-Intel-Exporter, before SuperBrain passthrough.
- **Processing summary:** Four independent trigger detectors — T1 `VOL_COMPRESSION`, T2 `VWAP_RECLAIM`/`VWAP_LOSS`, T3 `RANGE_BREAK`/`RANGE_BREAK_EARLY`, T4 `TRAP` — weighted into a score and quality tier.
- **Confidence/quality fields:** `trigger_score`, `trigger_quality` (STRONG≥3.5/SINGLE≥1.5/NONE), `trigger_go_eligible` (VWAP alone never qualifies), `eligible_for_trade`.
- **Gates/thresholds:** `QUALITY_STRONG_MIN=3.5`, `QUALITY_SINGLE_MIN=1.5`, `T1_COMPRESSION_MAX=0.45`, `T1_ATR_PERCENTILE_MAX=30.0`, `T2_VOLUME_RATIO_MIN=1.1`, `T3_EARLY_ADX_MIN/MAX=18.0/28.0`, `T3_CONF_ADX_MIN=25.0`, `TRIGGER_MAX_AGE_SESSIONS=2`.
- **Prior claim(s):** in-code changelog documents a historical bug where this stage originally only patched package JSONs, not the EIL CSV, causing `ede_trigger_count=0` for all 1,470 signals and a superseded sovereign gate firing WAIT universally — **CONFIRMED FIXED** (see the post-EIL re-run of this stage below: 74.8% go-eligible today, not zero).
- **Perceived efficiency gap:** Low for this stage in isolation (coherent, fixed). The real gap is entirely downstream.
- **Card confidence:** High. *(Agent 2)*

### Stage: SuperBrain Passthrough (Phase 8d)
- **Processing summary:** SuperBrain's own scoring was deprecated 2026-04-28 ("migrated to OI"). This function is now a **pure passthrough/shim**: copies the OI CSV, maps `options_verdict → sb_final_verdict` if absent, inserts NaN placeholders for spread/contract columns EIL's liquidity gate needs. Retained deliberately — "Do NOT remove — EIL/GARCH/WBS/CT Gate require superbrain_enriched to exist." **CONFIRMED** by direct read: no new scoring occurs.
- **Perceived efficiency gap — Low:** honestly labelled dead-logic-retained-as-plumbing; worth noting only because the "SuperBrain" name in docs/tests may mislead a reader into expecting live scoring here.
- **Card confidence:** High. *(Agent 2)*

### Stage: Catastrophe Gate (Phase 8b — name collision with Options Intelligence's own "Phase 8b" label)
- **Processing summary:** Pure no-op stub. In-code docstring: "Sprint 2: Catastrophe Gate removed from live decision chain. Was running in shadow mode with no measured outcome contribution." Returns `True` unconditionally — confirmed by reading the full 11-line function body.
- **Perceived efficiency gap — Low:** honestly retired, no hidden cost; the phase-label collision is a minor cross-referencing friction, not a confidence issue.
- **Card confidence:** High. *(Agent 2)*

### Stage: Wall Break Scorer (Phase 8e, `wall_break_scorer.py`)
- **Trigger:** After Catastrophe Gate no-op.
- **Processing summary:** Scores every EXECUTE/EXECUTE_WITH_RISK signal on a 5-factor Wall Break Score (vanna, wall weakness, flip clearance, vol loading, momentum alignment) — is the position has structural energy to push through the gamma wall.
- **Confidence/quality fields:** `wbs_score`, `wbs_grade` (IMMINENT≥75 "full campaign + 25% boost, enter immediately" / PROBABLE≥55 "full campaign, patient entry" / POSSIBLE≥35 "50% size" / UNLIKELY<35).
- **Verification method:** code read + run artefact — today: 81 rows (matches OI's 81 EXECUTE rows exactly); `wbs_grade`: PROBABLE 39, POSSIBLE 35, UNLIKELY 5, **IMMINENT 2**.
- **Perceived efficiency gap — HIGH:** the clearest concrete illustration of the PSE finding below — 41 rows are explicitly graded "full campaign, enter immediately/patiently" by a purpose-built structural-energy scorer, and every one of them gets `pse_final_size=0.0` two stages later. WBS is doing its job correctly; its output has nowhere to land with authority. Additionally: no code in `execution_intelligence_runner.py` was found reading `wbs_grade`/`wbs_score` at all (grep returned no hits in sizing-assignment sites) — **could not fully verify** whether WBS grade is even consumed downstream by name, separate from the sizing-zeroed issue.
- **Downstream consumer:** nominally capital-sizing decisions per its own docstring; not confirmed actually read by any sizing code.
- **Card confidence:** Medium. *(Agent 2)*

### Stage: Pre-EIL Actuarial Injection ("FIX-ACTUARIAL-SEQ")
Re-injects actuarial columns into `superbrain_enriched` specifically because EIL's `EVEngineV2` reads them directly and would otherwise see blanks. Documented, working fix. *(Agent 2)*

---

## ★ Headline finding — Execution Intelligence Layer / Position Sizing Engine (Phase 9)

**EV3, macro, and legacy R:R carry zero capital authority — and so does every other scoring layer in the signal-engine range, because the single component that would convert confidence into position size, `position_sizing_engine.py`, is hard-disabled in the only code path that calls it.**

### Stage: EIL (`execution_intelligence_runner.py`)
- **Trigger:** After the pre-EIL actuarial injection.
- **Inputs:** `superbrain_enriched_{run_id}.csv` (actuarial pre-injected). Uses `EVEngineV2` (`ev_engine_v2.py`), **not EV3** (confirmed by import).
- **Direct code evidence:**
  - `execution_intelligence_runner.py:220-222` — `_pse_compute = None`, `_PSE_AVAILABLE = False` hardcoded unconditionally (not an import-failure fallback — a deliberate stub), `PSE_RETIRED_POLICY = "PSE_IGNORED_MANUAL_SIZING"`.
  - Every one of 20+ assignment sites for `row["pse_final_size"]` across the file sets it to literal `0.0`. No code path ever writes non-zero.
  - `position_sizing_engine.py:1-17` self-documents: `STATUS: RETIRED / NOT ON ORCHESTRATOR PATH (capital authority)`.
  - `vanguard/ev_engine_v3.py:1-6`: "`ev3_capital_eligible` remains false until a separately calibrated capital policy is approved."
  - `scripts/apply_ev3_authority.py:153` — `authority_active = False` hardcoded; the `--enable-authority` CLI flag is documented "Deprecated compatibility flag; EV remains advisory only."
  - `intelligent_orchestrator.py:437-440` — `EV3_AUTHORITY_ENABLED = False` is a separate hardcoded constant that nothing derives from the env-var-driven "requested" flag.
  - `execution_gate.py` — grepped for `ev3|ev_engine|ev_adjusted|expected_value|macro`: **zero matches**. `position_sizing_engine.py` — grepped for the same EV3 terms: **zero matches**.
- **Direct run-artefact evidence (today):** `execution/execution_v3_5_20260829_100803.csv` — 1,316/1,316 rows `pse_final_size=0.0` and `fd_size=0.0`. `capital_permission` values present: `WATCH_ONLY` (610), `NO` (468), `EOD_CANDIDATE_ONLY` (238) — **no row carries a capital-granting value.** Of the same run's 81 `options_verdict=EXECUTE` rows, 41 are graded IMMINENT/PROBABLE by Wall Break Scorer as "ready for full-campaign entry" — **all 41 still receive `pse_final_size=0.0`.**
- **Confidence/quality fields:** `pse_execution_mode`, `pse_final_size` (always 0.0), `capital_permission`, `campaign_verdict`, `kelly_verdict`.
- **Verification method:** code read (targeted, full for the sizing-relevant sections) + run artefact checked directly (1,316/1,316 rows).
- **Perceived efficiency gap — CRITICAL / HIGH:** the "no new trades" state is not (only) a confidence-threshold problem — it is architectural. Even a signal that clears every gate in the signal-engine range (Options Intelligence EXECUTE, Trigger Layer GO-eligible, WBS IMMINENT) cannot generate a sized trade today, because the valve that turns a verdict into a position size returns zero unconditionally. **Raising confidence will not by itself resume live execution** — PSE's retirement would need to be separately reversed, and reversal is itself gated on calibration evidence (`matched_outcome_rows ≥ 30`) that can't accumulate without trades. This is a closed loop, and the single highest-value finding of this whole investigation for the stated business objective.
- **Card confidence:** High. *(Agent 2)*

---

### Stage: GARCH Runner (`garch_runner.py`) — labelled Phase 10a/10b, runs immediately after EIL specifically so its output reaches `eil_enriched`
- **Trigger:** `run_garch_layer()` after EIL succeeds.
- **Processing summary:** Fetches 252 trading days of OHLCV per ticker, calls `layer3_forward_variance.compute_forward_variance()`. Primary method HAR-RV; EWMA_FALLBACK/ATR_PROXY are degraded paths for thin history. `_audit_garch_result()` is audit-only, never mutates values — a documented fix (RC-7) that removed a prior sanitiser that silently replaced correct HAR-RV forecasts with inferior EWMA estimates.
- **Outputs:** `qomega/garch_forecasts_{run_id}.csv` — `l3_method`, `l3_forward_realised_vol`, `l3_vol_forecast_conf`, `l3_iv_tailwind_score`, `l3_n_bars`.
- **Verification method:** code read + run artefact — today: **1,316/1,316 rows (100%) used `l3_method=HAR_RV`**, zero fallback usage, zero failures.
- **Efficiency gap:** Low — clean, full coverage, no degraded-path usage today.
- **Downstream consumer:** SuperBrain/EIL merge; morning_gate Check 7 (Layer 3 model risk).
- **Card confidence:** High. *(Agent 3)*

### Stage: Trigger Layer — post-EIL CSV enrichment ("Phase 8.6b" — runs after Phase 9/10 despite its label)
- **Trigger:** After GARCH merge, explicitly documented: "POSITION FIX: Phase 8.6 now runs AFTER EIL (Phase 9) so eil_enriched CSV exists when enrich_csv() is called."
- **Processing summary:** Re-injects trigger input + Vanguard governance columns into `eil_enriched` (which otherwise carries zero of them), re-evaluates T1-T4, writes flat columns directly into `eil_enriched`.
- **Verification method:** code read + run artefact — today: `trigger_go_eligible` True=985 (74.8%), `trigger_quality`: SINGLE=684, NONE=331, STRONG=301, zero stale rows.
- **Prior claim(s):** the wiring-gap bug this stage fixes is documented in the orchestrator's own changelog — **CONFIRMED FIXED**, a genuine, verified positive.
- **Perceived efficiency gap:** Low for the mechanism (works as documented). **High**, restated: 74.8% GO-eligibility here, 0% capital sizing at the stage immediately upstream — the gap is not in this stage. Its real terminal consumer in the live path is nothing with capital authority (the orchestrator's own comment: "Phase 9.5 EDE: SUPERSEDED — PSE inside EIL runner is the replacement," and that in-runner PSE zeroes everywhere).
- **Card confidence:** High. *(Agent 2 + Agent 3, cross-confirmed)*

### Stage: Catalyst Truth Layer (post-EIL, `catalyst_truth_engine.py`)
- **Trigger:** `run_catalyst_truth_layer(stage="post_eil")`; re-run again at `stage="pre_morning_validation"` since the first pass predates `morning_candidates` existing.
- **Processing summary:** Explicitly labelled "shadow/advisory enrichment pass. It does not allocate capital." Scores 0-100 `catalyst_truth_score` and `event_convexity_score`, classifies `catalyst_trade_class`. Deliberately **excludes** pipeline direction fields from its own independent-evidence collector, with an explicit comment explaining this prevents double-counting toward Direction Governance's 2-family resolution rule.
- **Confidence/quality fields:** `catalyst_truth_score`, `catalyst_binary_score`, `event_convexity_score`, `catalyst_data_quality`, `catalyst_trade_class`, `catalyst_direction_bias`, `catalyst_direction_independent`.
- **Verification method:** code read + run artefact (`catalyst_truth_summary_20260829_100803.json`).
- **Perceived efficiency gap — HIGH:** today: `catalyst_detected = 15/1528 (1.0%)`, and **all 15** came from manually-uploaded calendar data — **zero** organically inferred. `STRUCTURE_ONLY_NO_CATALYST = 1513 (99.0%)`. This starves Direction Governance's CATALYST evidence family for all but a handful of tickers, increasing the population of ambiguous rows that get blocked before an option-chain request (see EOD Candidate Engine dropoff evidence below).
- **Downstream consumer:** `direction_governance.resolve_governed_direction()`, `handoff_contract_audit.py`, EOD Candidate Engine, morning_gate.
- **Card confidence:** High. *(Agent 3)*

### Stage: McMillan Advisory Layer (Phase 9D, `mcmillan_advisory_layer.py`)
- **Trigger:** After Catalyst Truth.
- **Processing summary:** Three read-only advisory lenses — IV/GEX entry-quality, expected-move-vs-theta-drag, "crowd arrival" state. Docstring: "intentionally read-only with respect to decisions: no filtering, no sizing, and no verdict changes" — **confirmed** by code read (no filter/mask/verdict logic anywhere in the module).
- **Confidence/quality fields:** `iv_gex_entry_quality` (1-4), `crowd_arrival_score` (0-3).
- **Verification method:** code read + run artefact (`handoff_contract_audit` shows 7 McMillan fields `PRESENT_BUT_EMPTY` in `shadow_book` for 288 rows — WARN, not FAIL, consistent with advisory-only).
- **Perceived efficiency gap — Low:** working as designed; the shadow_book gap is cosmetic and correctly flagged WARN by the audit itself.
- **Downstream consumer:** EOD Candidate Engine's "McMillan safety net" rescue-join, Lab display only.
- **Card confidence:** High. *(Agent 3)*

### Stage: EOD Candidate Engine (Phase 10, `eod_candidate_engine.py`)
- **Trigger:** After McMillan, non-critical.
- **Inputs:** `execution/execution_v3_5_{run_id}.csv` — code comment explicitly warns the parameter name `eil_path` is legacy and this is "deliberately the final execution artifact, never the earlier EIL frame."
- **Processing summary:** `build_candidate_manifest()` writes the single manifest morning validation reads, then five sequential in-place patches: B1 FIX (real-missing-value-mask Greeks coalescing), B4 FIX (re-joins `l3_*` GARCH fields), McMillan safety net, MACRO EXPOSURE stamp ("DISPLAY ONLY — must NEVER be read by scoring or execution code"), B3 Exit Rules Engine.
- **Outputs:** `morning_validation/morning_candidates_{run_id}.csv` — **817 rows today.**
- **Gates/thresholds:** if `execution_v3_5_{run_id}.csv` doesn't exist, the manifest is skipped **fail-closed** with a logged error — no silent empty fallback.
- **Verification method:** code read + run artefact — `candidate_tier_counts`: WATCH 657, B 77, C 72, A 11; `execution_capital_counts`: WATCH_ONLY 610, NO 468, EOD_CANDIDATE_ONLY 238.
- **Perceived efficiency gap — HIGH, the single biggest volume bottleneck in the whole funnel:** cross-referencing `dropoff_audit_20260829_100803.json` (same run): of 1,527 Discovery-selected tickers, **1,010 (66.1%) are dropped at the OPTIONS_INTELLIGENCE stage** with root cause `NO_USABLE_OPTIONS_CONTRACT` — top reason "No contract passed quality gates" (651), second "No governed long CALL/PUT direction; chain request suppressed" (333, direct consequence of the direction-governance fail-closed design plus the catalyst-evidence starvation above). Only 817/1,527 (53.5%) reach `morning_candidates` at all; of those, only 238 (29.1%) get `capital_permission=EOD_CANDIDATE_ONLY`. This dwarfs every downstream confidence-score gate in raw volume — options-contract liquidity/quality, not any confidence threshold, is the dominant reason candidates never reach morning validation.
- **Downstream consumer:** `pipeline_integrity`, `dropoff_audit`, `handoff_contract_audit`, `uat_audit_report`, morning_gate.
- **Card confidence:** High — corroborated by three independent same-run artefacts. *(Agent 3)*

### Stage: Pipeline Integrity Report ("FIX-INTEGRITY v3.3")
- **Processing summary:** Computes `manifest_permission` (e.g. `MORNING_VALIDATION_REQUIRED`, `REVIEW_ONLY_ACTUARIAL_DEGRADED`, `BLOCKED_ACTUARIAL_AND_HORIZON_MISSING`) from actuarial-fill-rate, horizon-routing-presence, tier-A/B/exec-ready counts. Carries EV3-shadow health as explicitly non-authoritative telemetry ("never changes manifest permission during shadow validation").
- **Verification method:** code read + run artefact — today: `manifest_permission="MORNING_VALIDATION_REQUIRED"`, matches `final_run_manifest.json`'s `run_execution_permission`.
- **Card confidence:** High. *(Agent 3)*

### Stage: Diagnostics/Archive (`dropoff_audit.py`, `handoff_contract_audit.py`, `uat_audit_report.py`, `market_context_diagnostics.py`, archive/prune) — unnumbered in code
- **`dropoff_audit.py`** — tracks all 3,320 universe tickers through every stage with `last_stage_reached`, `dropoff_stage`, `root_cause_family`, `audit_severity`. Read-only, no gates. The single most valuable artefact for the confidence-lineage/efficiency question this investigation asked. High confidence.
- **`handoff_contract_audit.py`** — field-presence/fill-rate checker across 7 downstream artefact stages plus 3 semantic-contradiction checks (options-permission allowlist, no EOD-promotion for hard-vetoed rows, retired PSE policy must carry zero size). Diagnostic only, does not block. Today: `overall_status=WARN, fail_count=0, warn_count=8` (all McMillan-field emptiness in `shadow_book`, cosmetic). High confidence.
- **`uat_audit_report.py`** — aggregates the two audits above into one human-readable report. Medium-High confidence (artefact read in full, aggregation source not line-read).
- **`market_context_diagnostics.py`** — sector breadth + intraday regime watchdog, both self-labelled `advisory_only: true, mutates_pipeline_outputs: false`; watchdog inactive by design for EOD-mode runs. Confirmed never touches candidate output. High confidence.
- **Archive/Prune/manifest write** — `write_final_run_manifest()` (today: `run_health_score=97`, `next_action="NEEDS_MORNING_VALIDATION"`, `run_tradeable=false`), `write_final_opportunity_book()` (feeds the Lab), retention pruning (47/90 runs present, no pruning needed today). High confidence.
*(Agent 3)*

---

## ★ Today's run stops here

**Direct evidence:** `final_run_manifest.json` shows `morning_validation: "PENDING"`, `row_counts.morning_validation=0`, `next_action="NEEDS_MORNING_VALIDATION"`. `logs/orchestrator.log`'s last lines (11:43:38 today) end with "EVENING WORKFLOW COMPLETE ... Next: python morning_gate.py --run-id 20260829_100803." No `morning_validated_trades_20260829_100803.csv` exists anywhere. **`morning_gate.py` has not been run against today's run as of this investigation.** This is itself a finding: the "no new trades" state observed today may be partially or fully explained simply by morning validation not having executed yet, independent of any confidence-quality question. All morning-side evidence below therefore uses the most recent completed morning run, **2026-08-28** (`data/output/runs/20260828_094349/`), clearly marked. *(Agent 3)*

---

## morning_gate.py — 8 checks (not 5; prior doc CONTRADICTED)

`docs/pipeline_map/06_MORNING.md` (2026-08-20) describes 5 checks, v1.2, with Execution Gate called directly from the orchestrator. Current code (modified today, v1.3) has 8 checks and routes Execution Gate through the shared `morning_handoff_finalizer.py` (a real hardening consolidation, not a regression). Real verdict priority order in code: authority → direction integrity → production-strategy eligibility → contract-repair-in-progress → monetisability → invalidation → spread policy → contract liquid → layer-3 model risk → else GO.

### Stage: Check 0 — Upstream Authority
- **Gate:** requires `authority_source_stage=="FINAL_EXECUTION"`, `final_route` not blocked/equity-only, `capital_authorization_state`/`capital_permission=="EOD_CANDIDATE_ONLY"`, `eod_candidate_authorized` truthy. All written upstream by EIL (Phase 9), not by morning_gate itself.
- **Verdict on fail:** `BLOCK`, `route="STAND_DOWN_UPSTREAM_AUTHORITY"`. Highest verdict priority.
- **Verification method:** code read + run artefact (Aug 28: `morning_validated_trades_20260828_094349.csv`).
- **Real-run evidence (Aug 28):** `FALSE` for **594/819 rows (72.5%)**, all `UPSTREAM_NOT_AUTHORIZED:NOT_AUTHORIZED` — by far the dominant BLOCK reason in the whole gate.
- **Perceived efficiency gap — HIGH:** a Phase-9-EIL-side symptom, not a morning_gate defect, but it means the other 7 checks are only exercised on ~a quarter of candidates.
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 1 — Monetisability
- **Gate:** `monetisability_state` must be `MONETISABLE` or `LIMITED`; `NOT_MONETISABLE`/missing → BLOCK.
- **Real-run evidence (Aug 28):** of the 225 authority-passed rows, `morning_execution_lane=NON_MONETISABLE` for 77 (34.2%) — second-largest block reason after authority.
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 2 — EV3 Evidence
- **Gate:** `_check_ev3_authority()` **always returns `True`** — confirmed, no branch can return `False`. Advisory text-only, consistent with the EV3-no-authority finding above.
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 3 — Invalidation Intact
- **Gate:** no `live_price` → `FLAG` ("live price unavailable"), not BLOCK. CALL price ≤ invalidation (or PUT ≥) → `BLOCK` ("thesis broken"). No invalidation on record → passes with WARN.
- **Verification method:** code read; not separately isolated in run-level stats — **partially verified**.
- **Card confidence:** Medium. *(Agent 3)*

### Stage: Check 4 — Macro Context
- **Gate:** `macro_pass` is a **hardcoded `True` literal** — display/context only, matching the docstring's explicit framing (not a verdict input).
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 5 — Contract Liquid
- **Gate:** live bid/ask required; spread ≤ `executable_spread_max_pct` clean-pass else `review_max_pct` hard cap (governed, cannot be relaxed by CLI beyond the governed max); delta within `[0.20, 0.70]` absolute; IV `>0` and `≤250%`; live-vs-EOD IV compression ratio `<0.70` triggers FLAG ("premium actively deflating"), not block.
- **Real-run evidence (Aug 28):** of 198 rows with a contract to check, 190 (96.0%) got a real MarketData.app quote; 8 (4.0%) failed even after repair alternatives.
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 6 — Bond Macro Context
- **Gate:** `bond_pass` computed from `bond_trade_go` (26h staleness window) but **never referenced anywhere** in the block/flag-reason construction (exhaustively read) — fully advisory, matching its docstring.
- **Card confidence:** High. *(Agent 3)*

### Stage: Check 7 — Layer 3 Model Risk
- **Gate:** `_layer3_model_risk_guard()` flags `VOL_HARDCAP` (≥2.50), `LOW_CONF_HIGH_VOL` (conf≤65 & vol≥1.50), `THIN_HISTORY` (<100 bars), `IV_TAILWIND_EXTREME` (|tailwind|>1.50). Any flag → `FLAG`, `route="MODEL_RISK_REVIEW"` (not BLOCK).
- **Card confidence:** Medium-High. *(Agent 3)*

### Stage: Live-quote/equity hydration (`_fetch_all_live()`, morning_gate.py)
- **Inputs:** Polygon `/v2/snapshot/.../tickers/{ticker}` for equity price (direct urllib, own key — **does not use `polygon_data_fetcher.py`**, confirmed by grep: zero references); MarketData.app for option quotes.
- **Could not verify a "today" figure — today's run has not reached morning_gate.** Most recent actual figures (Aug 28, direct pandas aggregation over morning_gate's own stamped fields): equity fetch 819/819 (100%) succeeded; among the 198 rows that ever attempt an options-contract quote, 190 (95.96%) succeeded, 8 (4.04%) failed after repair attempts; contract-repair-alternative success rate 29.4% (30/102 attempted). **The larger structural point:** only 198/819 (24.2%) of candidates ever reach the point of attempting a live options quote at all — 621/819 (75.8%) are blocked earlier (mostly Check 0). The *effective* hydration failure rate against all candidates is much lower than the raw 4% suggests in isolation, because most rows never get that far — itself the dominant efficiency issue (see EOD Candidate Engine dropoff above).
- **Card confidence:** Medium-High for Aug 28 figures; explicitly unverifiable for today. *(Agent 3)*

---

## morning_handoff_finalizer.py / execution_gate.py — effectively "Phase 11" per the orchestrator's own code comments

- **Trigger:** called identically by both `premarket_workflow()` and `morning_gate.py`'s own CLI — module docstring: "Both supported Morning entry points call this module so a Morning run cannot report success while leaving the Intelligence Lab on the previous EOD view."
- **Processing summary:** runs `execution_gate.run_execution_gate()`, then `write_final_run_manifest()`/`write_final_opportunity_book()`, then `_execution_lab_mismatches()` — a **fail-closed row-by-row reconciliation**: ticker-set equality, `final_action`→`lab_verdict` mapping correctness, contract-identity equality, and direction-field-hash equality (`dir_calc_version`, `governed_direction`, `final_direction`, `governed_direction_record_sha256` must match exactly). Any mismatch raises `MorningHandoffError` and the whole workflow reports failure.
- **`execution_gate.py`:** delta/spread/IV/runway/gamma-flip soft-penalty gates; hard blocks only on spread `>15%` and delta outside `[0.20, 0.85]`. Its own live-quote fallback (`get_live_option_data()`) is a **permanent stub** that always returns `{}` and logs a one-time warning — low-impact in practice because it only fires when morning_gate itself already failed to get a quote (already-non-actionable rows).
- **Verification method:** code read + run artefact (Aug 28 `morning_handoff_summary_20260828_094349.json`).
- **Real-run evidence (Aug 28):** `status=PASS`, `execution_lab_exact_match=true`, `execution_lab_mismatch_count=0`, `direction_version_uniform=true` (`dir_v1.1.0`), `morning_authority_preserved=true`. `execution_gate` action counts: BLOCK=402, BUY_NOW=35, BUY_SMALL=40, CONTRACT_REPAIR=300, MANUAL_REVIEW=42 → actionable rate **9.16% (75/819)**. Interpreter sync verified via SHA-256 match on all 4 required artefacts.
- **Card confidence:** High. *(Agent 3)*

## Direction Governance — dedicated verification (CONFIRMED)

`contracts/direction_governance.py` (modified 2026-08-27, `DIR_CALC_VERSION="dir_v1.1.0"`, one version ahead of the doc's cited `dir_v1.0.0` — confirming continued iteration since the doc was written).
- `structural_direction()`: `precor_intent=WAIT` → `UNRESOLVED`; unknown intent → `UNRESOLVED`; mixed/unclear TRANSITION → `STRANGLE`. **No branch returns CALL for an unhandled/ambiguous case.**
- `preliminary_discovery_direction()`: docstring literally states "Return a preliminary hint without ever defaulting ambiguity to CALL" — returns `UNRESOLVED` if neither fusion nor Wyckoff direction is directed.
- **Wired into production, confirmed by grep + read:** `avshunter_discovery_ULTIMATE.py:46,1577-1583` calls this with a comment "Ambiguity is UNRESOLVED by construction; it must never default to CALL." `scripts/avshunter_options_intelligence.py:3624-3640` calls `structural_direction()` then `resolve_governed_direction()`.
- `resolve_governed_direction()`: a STRANGLE/UNRESOLVED direction can only be upgraded to a directed `final_direction` if ≥2 independent evidence families agree, `winning_share≥0.60`, `margin≥0.20` — otherwise stays non-directional (`resolution_path="UNRESOLVED"`).
- `validate_direction_record()` (called by both morning_gate and `execution_gate.py`) independently re-verifies the SHA-256 hash, policy version, evidence-family count, thresholds, and target/invalidation sign-consistency — a genuine second enforcement point.
- **Run evidence (Aug 28):** `governed_direction` distribution CALL 420, PUT 343, STRANGLE 55, UNRESOLVED 1 (819 total). All 56 non-directional governed rows were successfully evidence-resolved to a directed `final_direction` this run (no case exercised the "insufficient evidence, stays UNRESOLVED" branch this particular run — the mechanism is present and code-verified, just not exercised by this run's evidence mix). `check_direction_integrity_pass=FALSE` for 353/819, but the dominant reason (344/353, `CALL_TARGET_NOT_ABOVE_SIGNAL`) is a target/invalidation-consistency failure, not a direction-defaulting bug.
- **Verdict: CONFIRMED** — the mechanism is live, wired at both origin points, independently re-validated at three further points, and the doc's own self-declared promotion-boundary criteria are met in the freshest available run. *(Agent 3)*

---

## Governed Book Construction and Intelligence Lab (Agent 4)

### Stage: Governed Book Assembly (`build_final_opportunity_book`/`opportunity_book_row`/`write_final_opportunity_book`, `contracts/lab_control.py`)
- **Trigger:** two producers converge on the same code — `intelligent_orchestrator.py` (EOD path, unconditional, try/except) and `morning_handoff_finalizer.py` (after `run_execution_gate()`).
- **Inputs:** `morning_candidates_{run_id}.csv` → fallback `eil_enriched_{run_id}.csv`; `_enrich_lab_extract_rows_from_run_sources()` merges up to 9 additional source CSVs with a field-level authoritative-source priority table.
- **Processing summary:** every row passed through `apply_lab_resolution()`/`resolve_lab_tradeability()` for `lab_verdict`/`lab_tradeable`/gate flags, then `opportunity_book_row()` maps ~297 named fields via alias chains, sorts by verdict-priority then `priority_score`, writes CSV+JSON with per-row `field_provenance_json`.
- **Outputs:** `final_opportunity_book_{run_id}.csv/.json` (297 columns/keys, identical across all 817 rows today), `lab_triage_view_{run_id}.csv` (296 columns).
- **Confidence/quality fields:** the full 297-field register (rank/verdict spine, direction confidence, composite/priority, EV3, actuarial/catalyst, physics/regime, EIL, trade economics, options/greeks, structure/wall, GARCH, convexity, readiness synthesis, trigger, vetoes/advisory, monetisability) — see `confidence_lineage.md` for the complete list.
- **Gates/thresholds:** `LAB_EXECUTABLE_SPREAD_MAX_PCT=18.0`, `LAB_ABSOLUTE_SPREAD_MAX_PCT=25.0`; `MORNING_VALIDATION_REQUIRED` fires exactly when `pipeline_mode=="EOD" and not morning_present and "EOD_MISSING_MORNING_VALIDATION" in soft and not veto_flags` — the literal, deliberate, non-buggy reason 808/817 rows in today's run are gated to `MORNING_VALIDATION_REQUIRED`.
- **Verification method:** code read + live artefact checked field-by-field, row-by-row (Python) against `final_opportunity_book_20260829_100803.json/.csv`.
- **Prior claim(s):** `docs/INTELLIGENCE_LAB_FUNCTIONALITY_DATA_ROADMAP.md`'s "232 fields" claim — **CONTRADICTED** (live count 297; the doc's own cited reference run is actually 185 fields when opened directly — the doc was already internally inconsistent). `docs/pipeline_map/08_SYNTHESIS.md`'s "`campaign_verdict` computed then dropped, never written to any CSV" — **CONTRADICTED at this stage** (populated on all 817/817 rows today, sourced via `morning_candidates`/`eod_candidate_engine.py`, a different path than the one the prior audit examined — both claims can be simultaneously true about different stages).
- **Perceived efficiency gap — Medium:** field-count documentation drift (232/297/185) means any guide built off the stale doc misdescribes what the trader can actually see.
- **Downstream consumer:** Intelligence Lab (`_governed_lab_book()`), `ma_inputs_sync.py` via triage view.
- **Card confidence:** High. *(Agent 4)*

### Stage: morning_gate → Lab interface — dedicated check: **MATCH**
`morning_gate.py::main()` calls `morning_handoff_finalizer.finalize_morning_handoff()`, which runs `run_execution_gate()` then calls `write_final_opportunity_book()` — the identical producer/schema the orchestrator's own EOD path also calls. For today's run, all 817 rows carry `pipeline_mode="EOD"` and no `morning_validated_trades` file exists — confirming the run only went through the EOD path, consistent with the "morning_gate not yet run" finding above, not a contradiction of it. *(Agent 4)*

### Stage: Lab UI Consumption (`intelligence-lab/intelligence_lab.py`, `static/index.html`, `static/AVSHUNTER_sector_ui_patch.js`)
- **Trigger:** any request to the Lab's run-data endpoint for a given `run_id`.
- **Inputs:** `final_opportunity_book_{run_id}.json`, gated on `lab_schema_version=="lab_signal_book_v2"` and row-count match — today the governed path was used (`lab_signal_source=="GOVERNED_FINAL_OPPORTUNITY_BOOK_V2"`), UI receives the raw 297-field rows unmodified.
- **Verification method:** code read + systematic substring diff of all 297 field names against both UI source files, then targeted verification of specific mismatches by reading the render code and confirming the exact keys against a real row.
- **Perceived efficiency gap — HIGH, new finding:**
  - **159 of 297 governed fields never appear anywhere in the UI source**, including `win_prob_predicted`, `actuarial_confidence`, `actuarial_match_method`, `ev3_p_target/p_stop/p_timeout/n_effective/uncertainty_total_return`, `garch_forecast_confidence`, all five physics scores, `convexity_score/campaign`, and — most on-point for the objective — **`readiness_stage`/`readiness_label`/`readiness_enter_now`**, the exact field that already says, in plain text, why the system isn't trading today (`EOD_PREP_COMPLETE_MORNING_VALIDATION_REQUIRED` on all 817/817 rows). A trader opening the Lab today cannot see this computed, correct answer anywhere.
  - **A second, more serious defect: several UI panels read pre-governed legacy field names that don't exist in the current schema at all**, silently rendering defaults/blanks/zeros instead of the real, populated governed data one field-name away — verified directly against row 0 of the live artefact:
    - "Convexity Score" (9 separate UI locations, incl. the entire Convexity Engine tab) reads `s.sb_conv_score` — not a governed field. Real field `convexity_score` exists and is populated. The Convexity Engine tab additionally checks 5 `sb_c_*` sub-flags that don't exist in the schema at all — that tab is structurally non-functional against the current schema, always shows "0/8."
    - "Vetoes Fired" (13 occurrences) reads `s.sb_vetoes_count` — not a governed field (real fields: `hard_vetoes`/`options_hard_vetoes`). Always renders 0/"CLEAN" (coincidentally truthful today since both are empty on all 817 rows, but the code path is broken independent of that coincidence).
    - "Entry Reason" (4 occurrences) reads `s.sb_verdict_reason` — not a governed field. Real field `entry_reason` is populated (e.g. "Wyckoff SELL_SETUP vs actuarial CALL probability" for row 0) but never read by the UI. Always renders blank.
    - "Composite Score" in the modal overview reads `s.composite||s['doss__composite_score']` — neither exists; real field `composite_score` is populated (60.5 for row 0). Always renders `—`.
    - AVOID/STAGED campaign-count stats and funnel steps filter on `s.sb_campaign` — not a governed field (real field `campaign_verdict` is populated: AVOID=155, STAGED=11, REJECT=651 today). These specific counters always read 0, silently under-reporting 155 real AVOID and 11 real STAGED candidates. (The main verdict-based "Campaign" pill display is unaffected — it derives from `lab_verdict` via a lookup table, not `sb_campaign`.)
  - **Net effect:** a trader using the Lab today sees a false "0/8 Convexity," false-by-omission "0 vetoes / CLEAN," a blank Entry Reason, a blank Composite Score, and zero-count AVOID/STAGED stats — even though the underlying governed book has real, non-trivial values for every one of these. No fabricated data was found — the defect is real data present and correct on disk, invisible or misleadingly blank/zero on screen. This directly damages the objective's "internally consistent, free of unverified assumptions" bar: it will read to a trader as "the model has nothing to say" when it actually does, including the one field that already explains why no trades are firing.
- **Downstream consumer:** the trader, via Overview modal, KPI panel, Convexity Engine tab, watchlist cards, funnel/stats panel, CSV export.
- **Card confidence:** High — every mismatch verified by (a) reading the exact UI render line, (b) confirming the exact key is absent from a real governed row, (c) confirming the semantically-equivalent governed field exists and is populated in that same row. *(Agent 4)*

---

## Prior-claim resolution summary (Section 1 requirement — all five items)

| # | Prior claim | Verdict | Evidence |
|---|---|---|---|
| 1 | EV3, macro, and legacy R:R carry no capital authority | **CONFIRMED**, and shown to extend to *every* signal-engine layer (Phantom, WBS, Trigger Layer, SuperBrain) because PSE itself is hard-disabled | `execution_intelligence_runner.py:220-222`, 20+ `pse_final_size=0.0` sites, `position_sizing_engine.py` self-documented RETIRED, `apply_ev3_authority.py:153` hardcoded False, `execution_gate.py` zero EV3/macro references, 1,316/1,316 rows verified `pse_final_size=0.0` today |
| 2 | Direction-governance fix (ambiguity → UNRESOLVED, not CALL) is present and behaving as intended | **CONFIRMED** | Code read of `direction_governance.py` (no branch defaults to CALL), wired at both origin points, re-validated at 3 further points, Aug 28 run's own promotion-gate criteria (`morning_handoff_summary`) all pass |
| 3 | Current live-quote hydration failure rate | **PARTIALLY VERIFIABLE — today's run hasn't reached morning_gate.** Freshest available (Aug 28): 95.96% success among the 198/819 rows that ever attempt a quote; 100% equity-fetch success | `morning_validated_trades_20260828_094349.csv` direct aggregation |
| 4 | Actuarial observation count (~3.8M vs 5.9M+ prior figures conflict) | **RESOLVED — both real, different schema generations.** 3,816,857 = v7 (current production canonical); 6,033,072 = v6 (superseded rollback target) | Direct `pyarrow.parquet` row counts on both files, cross-checked against `actuarial_database_v7.validation.json` and today's `actuarial_last_run.json` |
| 5 | Governed-book field count (232 vs 297 prior figures conflict) | **RESOLVED — 297 is current.** The 232 figure's own source doc is internally inconsistent (its cited reference run is actually 185 fields) | Live count of `final_opportunity_book_20260829_100803.json` keys (297, all 817 rows identical) cross-checked against `contracts/lab_control.py`'s `FINAL_BOOK_FIELDS` (also exactly 297, same order) |

**Additional prior claims independently checked, not required but relevant:**
- Actuarial v6 registry fingerprint fix (2026-06-05) — **CONFIRMED still holding**, independently corroborated by both Agent 1 and Agent 2.
- Macro redesign graceful degradation (2026-05-22) — **CONFIRMED**.
- EIL trigger-column wiring-gap fix (historical `ede_trigger_count=0` bug) — **CONFIRMED FIXED**, 74.8% go-eligible today vs. the documented 0% before the fix.
- `docs/pipeline_map/08_SYNTHESIS.md`'s "campaign_verdict dropped, never written to CSV" — **CONTRADICTED** at the Lab-producer stage (populated today); reconciled as consistent with the prior finding being about a different, earlier write path.
- `docs/pipeline_map/06_MORNING.md`'s "5-check, v1.2 morning_gate" — **CONTRADICTED**; current is 8 checks, v1.3.

See `interface_gaps_register.md`, `confidence_lineage.md`, and `efficiency_gaps_register.md` for the remaining required deliverables.
