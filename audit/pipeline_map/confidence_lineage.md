# Confidence Lineage Trace — Macro Normalisation → Intelligence Lab

**Date:** 2026-08-29 | Companion to `PIPELINE_END_TO_END_MAP_20260829.md`

This traces every field carrying confidence/quality/score/verdict/rank semantics, in the order it is actually created or transformed, noting at each hop whether it carries **capital authority** (can size or gate a real trade) or is **advisory** (reports confidence but cannot itself deploy capital). The single most important fact this trace establishes: **almost the entire chain is advisory.** Capital authority terminates at exactly one gate — `pse_final_size` inside the Execution Intelligence Layer — and that gate is hardcoded to zero for every row, every run, today.

---

## 1. Macro Normalisation — the top of the chain

| Field | Producer | Nature | Capital authority |
|---|---|---|---|
| `macro_conviction` | `build_macro_json.py::call_macro_api()` — **live LLM call, model `claude-sonnet-4-6`**, prompted explicitly as "a confidence score 0-100" | **Subjective, uncalibrated.** No backtest/calibration evidence found. | No — feeds sizing multipliers downstream, but is itself the least-verifiable number in the whole lineage |
| `regime_probability` | same LLM call, equals `macro_conviction` in today's run | Subjective | No |
| `vix_regime_score`, `credit_risk_score`, `gex_regime_score`, `net_liquidity_score` | `build_macro_json.py::apply_market_data_overrides()` — deterministic, rule-based | Deterministic | No |
| `bond_macro_score`, `bond_macro_flag` | `bond_macro_intelligence.py::build_composite()` — deterministic (baseline 70, bounded deltas, clamped 0-100) | Deterministic, but **can be silently nulled** by `contracts/bond_macro_contract.py` when the yield-curve sidecar is stale (verified today: real 55/100 CAUTION score dropped to `None`/`PARTIAL_CONTEXT` in `macro_quant_packet.json` due to 2-session-stale FRED data) | No |
| `horizon_biases.{1_5d,6_10d,11_20d}.bullish_prob_pct` / `size_multiplier` | `macro_horizon_router.py` | **Derivative of `macro_conviction`** — inherits its unverified basis | No directly, but **is a real multiplier applied to whatever `pse_final_size` would have been** — currently moot since that base is always 0 |

## 2. Discovery

| Field | Producer | Nature | Capital authority |
|---|---|---|---|
| `wyckoff_score`, `crabel_score` | `avshunter_discovery_ULTIMATE.py` — technical scan | Deterministic | No |
| `composite_score` | `wyckoff*0.6 + crabel*0.4` | Deterministic | No |
| `tier`/`tier_label` | regime-adaptive thresholds (`tier1_min=50`, RISK_OFF requires ≥72) | Deterministic | No — but gates Discovery survival: only 18/1,527 (1.2%) reach Tier 1 today |
| `win_probability` | `calculate_win_probability()` — `min(75, max(35, 40 + composite*0.25))` | **Unexplained arbitrary linear heuristic** despite the name implying a calibrated statistic | No |
| state-prior adjustment (bounded ±15/-20) | `apply_state_prior_adjustment()`, cited as sourced from "3.7M cleaned actuarial observations" | Empirically-cited mechanism (bound verified; underlying bucket percentages not independently re-derived) | No |

## 3. Actuarial Cache/Query

| Field | Producer | Nature | Capital authority |
|---|---|---|---|
| `sample_size`, `state_match_quality`, `confidence_weight`, `actuarial_match_type` | `vanguard/layer2_statistical/actuarial_query.py` against `actuarial_database_v7.parquet` (3,816,857 rows, live-verified) | **Deterministic, empirically-grounded — the most trustworthy confidence machinery found in this investigation** | No |
| `layer2__probability_verdict` (NEGATIVE_EDGE/WEAK_EDGE/MODEST_EDGE/STRONG_EDGE), `layer2__probability_edge` | same | Deterministic | No — but today's population: 61.8% of packages score `NEGATIVE_EDGE`, only 6.4% `STRONG_EDGE`, likely the single strongest evidence for the "no trades" outcome at this early a stage |

## 4. External Intel Lane

`external_intel_source_tier`, `external_intel_macro_pressure_label`, `external_intel_data_quality` — additive tags only, verified structurally incapable of promoting a ticker into the core candidate set. No capital authority, no gating weight anywhere downstream.

## 5. Package Build — data-quality flags (broken as an audit signal)

`data_contract.{dcv_valid, dcv_confidence, dcv_bars}`, `data_failure`, `actuarial.deferred`/`reason` — **both stale-metadata bugs verified at scale** (100% and effectively-100% of sampled packages respectively carry stale/wrong values after later stages populate real data). Not consumed with authority anywhere; the one confirmed live consumer defensively bypasses `data_failure`. These fields should not be trusted as a data-quality signal by any future consumer.

## 6. Vanguard (Layer 1/2)

| Field | Nature | Capital authority |
|---|---|---|
| `state_hash`, `behaviour_state_hash` | Deterministic identity keys (two independently-defined 9/7-dim schemes — not the same as the Stage-8.5 actuarial-enrichment key set, a distinct third scheme; see Efficiency Gaps register) | No |
| `sample_confidence_bucket` | Deterministic, **documented as a required downstream gate** ("INSUFFICIENT_SAMPLE/CONTEXT_ONLY must never reach execution") but **not implemented as an enforced gate anywhere downstream** (verified by grep — zero hits in EIL/trigger/final-decision code) | No — and the documented safeguard is currently absent, latent risk if PSE is reactivated |
| `win_rate_{5,10,20}d`, `expected_value_{5,10,20}d`, `has_edge`, `edge_direction` | Deterministic, feeds `EVEngineV2` (advisory), not EV3 | No |

## 7. Options Intelligence

`options_verdict` (STAND_DOWN/ARMED/EXECUTE), `options_verdict_tier`, `final_route`, `options_research_score`, `contract_score`, `options_score` (OIS) — deterministic scoring/gating of contract selection. Governs whether a ticker is *eligible* to proceed but **carries no capital-sizing authority itself**; today 81/1,316 (6.2%) reach `EXECUTE`.

## 8. EV3 Governed Shadow — the most sophisticated layer, fully inert

`ev3_authority_state`, `ev3_monetisation_permission`, `ev3_ev_eligible`, `ev3_authority_active`, `capital_authority_calibrated` — a real barrier-crossing probability model (CRR/BSM) with an explicit calibration-readiness contract. **`authority_active` is a hardcoded `False` literal** (`apply_ev3_authority.py:153`), verified 1,316/1,316 rows today. Reactivation requires ≥30 matched outcomes; only 0 exist (14 journal outcomes, 0 matched) — a closed loop with the "no trades" state itself.

## 9. Actuarial Enrichment Pass (Phase 8.5)

`enriched_by`, `actuarial_fill_rate` — feeds `EVEngineV2` via a **second, independently-defined 9-dim state key**, distinct from Vanguard's own. No capital authority.

## 10. Phantom Scoring Engine

Phantom composite score — `PHANTOM_AUTHORITY_MODE = "ADVISORY_PROMOTION"` hardcoded, same closed-loop pattern as EV3 (promotion requires ≥1 week of live trading data). No capital authority.

## 11. Trigger Layer (package-patch pass)

`trigger_score`, `trigger_quality`, `trigger_go_eligible`, `eligible_for_trade` — deterministic detector logic (T1-T4), historically-documented wiring bug now confirmed fixed. No capital authority — feeds a superseded EDE stage.

## 12. SuperBrain Passthrough

`sb_final_verdict` — pure copy of `options_verdict`, zero new computation (SuperBrain's own scoring deprecated 2026-04-28). No capital authority, and no new information either.

## 13. Wall Break Scorer

`wbs_score`, `wbs_grade` (IMMINENT/PROBABLE/POSSIBLE/UNLIKELY, with literal grading language "enter immediately," "full campaign") — a genuinely well-engineered structural-energy scorer. Today: 41/81 EXECUTE-tier rows graded IMMINENT/PROBABLE. **Not confirmed read by any sizing code at all** (separate from the zeroing issue below) — flagged as a possible dead-end consumer, not just an inert one.

## 14. ★ EIL / Position Sizing Engine — the one true capital-authority gate, and it is closed

`pse_final_size`, `fd_size`, `capital_permission`, `pse_execution_mode`, `campaign_verdict`, `kelly_verdict` — this is the **only stage in the entire pipeline architected to convert a confidence/quality score into an actual position size.** `position_sizing_engine.py` is self-documented `STATUS: RETIRED`; `execution_intelligence_runner.py` hardcodes `_PSE_AVAILABLE = False` and every `pse_final_size` assignment to `0.0` (20+ sites, verified). Today: 1,316/1,316 rows `pse_final_size=0.0`, including all 41 WBS-IMMINENT/PROBABLE rows and all 81 Options-Intelligence-EXECUTE rows. **Every upstream confidence signal — real or subjective, deterministic or LLM-derived, well-calibrated or arbitrary — terminates here at zero.**

## 15. GARCH Runner

`l3_method`, `l3_vol_forecast_conf`, `l3_forward_realised_vol`, `l3_iv_tailwind_score` — deterministic volatility forecasting (HAR-RV primary, 100% coverage today, zero degraded-path usage). Feeds morning_gate Check 7 (advisory/FLAG only, not BLOCK). No capital authority.

## 16. Trigger Layer (post-EIL CSV pass, "8.6b")

Re-materialises the same trigger fields as flat columns in `eil_enriched` (74.8% go-eligible today). Confirmed real terminal consumer is nothing with capital authority (EDE superseded, PSE zeroed).

## 17. Catalyst Truth Layer

`catalyst_truth_score`, `event_convexity_score`, `catalyst_trade_class`, `catalyst_direction_bias` — explicitly self-labelled "does not allocate capital." Today: only 1.0% of tickers have catalyst evidence, 100% manually sourced — this starves the Direction Governance evidence pool for the vast majority of tickers. No capital authority; indirect volume impact on downstream gates.

## 18. McMillan Advisory Layer

`iv_gex_entry_quality`, `crowd_arrival_score` — confirmed by full code read to be genuinely read-only (no filter/mask/verdict-change logic exists in the module). No capital authority whatsoever, by design.

## 19. Direction Governance (invoked from Discovery + Options Intelligence, re-validated at morning_gate/execution_gate/Lab)

`direction_resolution_confidence`, `direction_resolution_call_score`/`put_score`/`winning_share`/`margin`, `direction_governance_status`, `governed_direction_record_sha256` — the one confidence mechanism in this trace that **does** gate (fail-closed): a STRANGLE/UNRESOLVED thesis cannot get an options chain requested at all unless ≥2 evidence families agree with sufficient margin. Confirmed live and correctly never defaults ambiguity to CALL. This gate blocks 333/1,010 dropped tickers today — a real, working confidence-based gate, just not a capital-sizing one.

## 20. EOD Candidate Engine

`structural_tier` (A/B/C/WATCH), `monetisation_fit_score`, `eod_candidate_status` — deterministic tiering of the 817 survivors. No capital authority (`capital_permission=EOD_CANDIDATE_ONLY` for only 238/817, itself downstream of the already-zeroed PSE field).

## 21. Pipeline Integrity Report

`manifest_permission`, `pipeline_technical_health`, `final_pipeline_state` — a meta-gate that downgrades the whole run's permission (e.g. to `REVIEW_ONLY_ACTUARIAL_DEGRADED`) if upstream normalisation degraded. Today: `MORNING_VALIDATION_REQUIRED`. Not itself capital authority, but does control whether the run may proceed to morning validation.

## 22. morning_gate.py — 8 checks, only 6 are load-bearing

`direction_resolution_confidence` (re-surfaced), `l3_model_risk_flags`, `contract_spread_policy_state`, `score_integrity_status`, and the terminal field for this stage: **`verdict`/`morning_execution_permission`/`morning_execution_route`.** Of the 8 checks, Check 2 (EV3) and Check 6 (bond macro) are confirmed advisory-only (their pass/fail values are computed but never enter the verdict-cascade `if` chain); the other six genuinely gate. Aug 28 evidence: Check 0 (upstream authority) alone blocks 72.5% of candidates that reach this stage — itself downstream of the same PSE/EIL authority chain (item 14).

## 23. execution_gate.py

`gate_size_penalty` (0.25-1.0 multiplier), `final_action` (BUY_NOW/BUY_SMALL/MANUAL_REVIEW/CONTRACT_REPAIR/BLOCK) — **the true terminal actionability field for the whole morning side.** Aug 28 actionable rate: 9.16% (75/819). This is real capital-relevant gating for the ~24% of candidates that reach it — but everything upstream of it already passed through the zeroed PSE valve, so `gate_size_penalty` is applied to a base size that was already forced to zero at item 14.

## 24. Governed Book (`contracts/lab_control.py`) — terminal synthesis, 297 fields

Every field above that survives to the trader-facing artefact is re-exposed here, plus new terminal-synthesis fields:
- **Rank/verdict spine:** `lab_rank`, `priority_rank`, `lab_verdict`, `lab_tradeable`, `lab_status`, `lab_execution_status`, `final_action`, `gate_reason`, `gate_warnings`, `eod_candidate_status`, `execution_category`, `campaign_verdict`, `lab_coherence_status`/`flags`
- **Direction confidence:** `direction_resolution_confidence`, `_call_score`, `_put_score`, `_winning_share`, `_margin`, `_evidence_count`, `direction_governance_status`, `direction_integrity_status`, `direction_conflict_status`
- **Composite/priority:** `composite_score`, `priority_score`, `liquidity_score`
- **EV3:** `ev3_status`, `ev3_data_state`, `ev3_absolute_state`, `ev3_p_target`/`p_stop`/`p_timeout`, `ev3_ev_conservative_return`, `ev3_ev_lower_bound_return`, `ev3_uncertainty_total_return`, `ev_predicted` — **all advisory, all traceable to the hardcoded-inert item 8 above**
- **Actuarial/catalyst:** `actuarial_match_method`, `actuarial_confidence`, `actuarial_sample_size`, `catalyst_truth_score`, `catalyst_direction_bias`, `win_prob_predicted`, `win_rate_source`
- **Physics/regime:** `market_energy_score`, `compression_energy`, `directional_force`, `force_alignment_score`, `trend_inertia`, `entropy_score`, `phase_transition_probability`, `regime_drift_status`
- **EIL:** `eil_signal_verdict`, `eil_v3_verdict`, `eil_composite_eod`
- **Trade economics:** `breakeven_price`/`pct`/`feasibility`, `option_gain_at_target`, `layer2__raw_prob_target_hit`, `layer2__adjusted_prob_target_hit`
- **Options/greeks:** `options_score`, `iv_rank`, `spread_pct`
- **Structure/wall:** `gamma_island_level`/`on_path`/`distance_pct`, `wbs`, `wbs_grade`
- **GARCH:** `garch_forecast_confidence`, `garch_iv_tailwind_score`, `garch_jump_risk_flag`
- **Convexity:** `convexity_score`, `convexity_campaign`
- **★ Readiness synthesis (the terminal plain-language answer to "why no trade"):** `readiness_stage`, `readiness_label`, `readiness_enter_now` — computed fresh here from `pipeline_mode + morning_data_state + lab_verdict/tradeable`. Today: `EOD_PREP_COMPLETE_MORNING_VALIDATION_REQUIRED` on all 817/817 rows.
- **Trigger:** `trigger_quality`, `trigger_score`, `trigger_codes`
- **Vetoes/advisory:** `hard_vetoes`, `options_hard_vetoes`, `advisory_flags`, `data_quality_flags`
- **Monetisability:** `monetisability_status`, `monetisability_state`, `monetisability_eligible`

Schema definition (`FINAL_BOOK_FIELDS` in `contracts/lab_control.py`) and the live artefact agree exactly at 297 fields, in identical order — the producer is internally consistent.

## 25. Intelligence Lab UI — where the trace visibly breaks

Of the 297 fields reaching the terminal artefact, **only ~138 (46.5%) are ever read by the UI source.** The 159 never-surfaced fields include `readiness_label` (item 24's terminal synthesis — the plain-language "why no trade" answer), all EV3 probability fields, `actuarial_confidence`, `garch_forecast_confidence`, and all five physics scores. Separately and more seriously, five specific UI panels (Convexity Score/Engine tab, Vetoes Fired, Entry Reason, Composite Score, AVOID/STAGED campaign stats) read **legacy field names that don't exist in the current 297-field schema at all**, so they render 0/blank/"—" in place of real, populated governed values one field-name away (`convexity_score`, `hard_vetoes`, `entry_reason`, `composite_score`, `campaign_verdict` respectively).

---

## Summary judgment on lineage integrity

The objective asks whether the confidence lineage is "complete, internally consistent, and free of unverified assumptions." Based on this trace:

- **Complete:** yes, mechanically — every stage's output was traced to the next, no orphaned fields, no unexplained gaps in the chain.
- **Internally consistent:** **mostly no.** Three concrete breaks were found: (a) three independently-defined actuarial/behaviour state-key schemes for what should be one concept, (b) two stale-metadata bugs where a field's value silently stops reflecting reality after a downstream stage updates the underlying data, (c) the Lab UI's legacy field-name reads, which make correct, consistent upstream data appear broken or absent at the very last hop a human sees it.
- **Free of unverified assumptions:** **no.** The master confidence figure at the top of the chain (`macro_conviction`) is an uncalibrated LLM judgment call, not a backtested statistic — the single largest unverified assumption in the lineage, and everything else, however well-engineered, sits downstream of it.
- **The dominant fact about the whole lineage:** it is architected almost entirely as an advisory reporting chain. Exactly one gate (`pse_final_size`) was ever meant to convert confidence into capital, and it is deliberately, verifiably zero everywhere, right now.
