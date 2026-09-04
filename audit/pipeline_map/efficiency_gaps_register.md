# Perceived Efficiency Gaps Register

**Date:** 2026-08-29 | Companion to `PIPELINE_END_TO_END_MAP_20260829.md`
**Business objective:** Raise signal confidence to the level required to safely resume live trade execution — measured by whether the confidence lineage this pack produces is complete, internally consistent, and free of unverified assumptions.

Ranked by business impact. Each entry names what would need to be checked or measured next to size a remediation — this register identifies, it does not fix.

---

## HIGH impact

### 1. Position sizing is hard-disabled system-wide — no signal, however confident, can generate a sized trade today
- **Stage(s) affected:** EIL / `execution_intelligence_runner.py` (Phase 9), `position_sizing_engine.py`
- **Business impact: HIGH.** This is the single most direct explanation for "no new trades" available anywhere in this investigation. `pse_final_size` is hardcoded to `0.0` at every one of 20+ assignment sites, unconditionally, for every row, every run — including the 41 rows Wall Break Scorer grades IMMINENT/PROBABLE ("enter immediately," "full campaign") and all 81 Options-Intelligence-EXECUTE rows today. Raising the *quality* of any upstream confidence score cannot change this outcome — the valve is closed by policy, not by score value.
- **Evidence:** `execution_intelligence_runner.py:220-222` (`_PSE_AVAILABLE=False` hardcoded), `position_sizing_engine.py:1-17` (self-documented `STATUS: RETIRED`), 1,316/1,316 rows verified `pse_final_size=0.0` in `execution/execution_v3_5_20260829_100803.csv`.
- **Prior status:** Not previously isolated as a single, system-wide, closed-loop finding in the docs reviewed — the retirement itself is documented in-code, but its full downstream consequence (every advisory layer's output terminating at one zeroed field) is a new synthesis of this pack.
- **Suggested next investigation:** Determine what evidence bar (calibration criteria, minimum outcome count, sign-off process) would need to be met to reverse PSE's retirement for even a narrow, small-size pilot lane — and separately, whether that evidence can be sourced from anything other than live pipeline trades (e.g. paper trading, manual seed trades) to break the closed loop.

### 2. `macro_conviction` — the master confidence score cascading into horizon sizing — is an uncalibrated LLM judgment, not a backtested statistic
- **Stage(s) affected:** Macro Normalisation (`build_macro_json.py`)
- **Business impact: HIGH.** This is the single largest unverified assumption sitting at the very top of the confidence lineage. It directly conflicts with the objective's "free of unverified assumptions" requirement — every downstream horizon-sizing multiplier inherits this uncertainty.
- **Evidence:** `build_macro_json.py::call_macro_api()` makes a live call to `anthropic.Anthropic()`, model `claude-sonnet-4-6`, prompted to output "a confidence score 0-100"; confirmed live in today's run (`macro_snapshot.json._builder_metadata.model="claude-sonnet-4-6"`). No calibration/backtest evidence found anywhere in scope.
- **Prior status:** New finding — not flagged in any prior audit reviewed.
- **Suggested next investigation:** Establish whether `macro_conviction`'s historical outputs have ever been backtested against realised regime outcomes; if not, size the cost/effort of building that backtest, or of replacing/supplementing the LLM call with a deterministic composite (the deterministic sub-scores already computed alongside it — `vix_regime_score`, `credit_risk_score`, `gex_regime_score`, `net_liquidity_score` — may be a starting point).

### 3. Today's run has not been through morning validation yet — process-state, not confidence-quality
- **Stage(s) affected:** Diagnostics/Archive → morning_gate.py boundary
- **Business impact: HIGH, but orthogonal to the objective.** Zero new trades today may be fully or partially explained simply by `morning_gate.py` not having run against today's EOD data — independent of any confidence-quality question this pack was asked to investigate.
- **Evidence:** `final_run_manifest.json`: `morning_validation: "PENDING"`, `next_action: "NEEDS_MORNING_VALIDATION"`; `logs/orchestrator.log`'s final lines (11:43:38 today) instruct the operator to run `morning_gate.py --run-id 20260829_100803` next; no `morning_validated_trades_20260829_100803.csv` exists anywhere.
- **Prior status:** New observation — not addressable by re-checking a prior claim, since it's a live process-state fact at investigation time.
- **Suggested next investigation:** None — this is an operational scheduling fact, not an audit finding requiring remediation. Noted here only because the objective explicitly asks findings to be held against "why no new trades," and this is a real, current, non-confidence-related contributor to that outcome today.

### 4. Options-contract-liquidity/direction-suppression gate is the dominant volume bottleneck, not any confidence threshold
- **Stage(s) affected:** Options Intelligence → EOD Candidate Engine boundary
- **Business impact: HIGH.** 1,010 of 1,527 Discovery-selected tickers (66.1%) are dropped before an executable option chain is even reached. This is a data/microstructure and evidence-availability constraint — raising signal confidence further will not move this bottleneck; it sits upstream of where confidence scoring even applies.
- **Evidence:** `dropoff_audit_20260829_100803.json`: root cause `NO_USABLE_OPTIONS_CONTRACT` — "No contract passed quality gates" (651), "No governed long CALL/PUT direction; chain request suppressed" (333). Only 817/1,527 (53.5%) reach `morning_candidates` at all.
- **Prior status:** Not previously quantified at this precision in the docs reviewed — new, artefact-verified figure.
- **Suggested next investigation:** Break down the 651 "failed quality gates" contracts by specific gate reason (spread, delta, OI, DTE) to determine whether the gate thresholds themselves are miscalibrated for the current universe's liquidity profile, or whether the universe genuinely lacks tradeable option structures for most Discovery candidates.

### 5. Discovery's own conviction funnel is severe: only 1.2% of candidates clear Tier 1, and 61.8% of packages score `NEGATIVE_EDGE` on actuarial edge
- **Stage(s) affected:** Discovery, Actuarial Cache/Query
- **Business impact: HIGH.** Strong direct evidence for "no new trades," established very early in the pipeline, well before execution gating. If this is the system correctly identifying that most candidates genuinely lack edge (the more likely read, given the actuarial machinery's evident rigor), it argues for accepting a naturally low daily trade count as correct behavior rather than raising confidence thresholds further. If it instead reflects overly conservative tier/edge thresholds, that is a distinct and separately actionable question.
- **Evidence:** `discovery_candidates_ultimate_20260829_100803.csv`: tier 1 = 18/1,527 (1.2%). Full-population aggregation across 1,528 packages: `layer2__probability_verdict=NEGATIVE_EDGE` for 944 (61.8%), `STRONG_EDGE` only 98 (6.4%).
- **Prior status:** New finding, population-level, not previously quantified.
- **Suggested next investigation:** Compare today's tier/edge distribution against a longer historical window (multiple runs) to establish whether 1.2%/61.8% is typical or anomalous for this universe and regime — a single day's snapshot cannot distinguish "correctly selective" from "miscalibrated."

### 6. Catalyst evidence is present for essentially no tickers — starves Direction Governance's evidence pool
- **Stage(s) affected:** Catalyst Truth Layer, Direction Governance
- **Business impact: HIGH** (compounds directly with #4). Only 15/1,528 tickers (1.0%) have any catalyst evidence today, and all 15 came from manually-uploaded calendar data — zero organically inferred. This starves one of the four evidence families Direction Governance's 2-family-minimum resolution rule relies on, increasing how often a thesis stays non-directional and gets its option-chain request suppressed.
- **Evidence:** `catalyst_truth_summary_20260829_100803.json`: `catalyst_detected=15/1528`, `trade_class_counts.STRUCTURE_ONLY_NO_CATALYST=1513 (99.0%)`.
- **Prior status:** New finding.
- **Suggested next investigation:** Assess why organic catalyst inference (from description/proximity heuristics, per the module's own design) detected zero events today — is this a genuinely quiet catalyst calendar, or is the organic-inference path itself broken/under-populated relative to its intended design?

### 7. Lab UI hides or misrepresents real, populated confidence data — including the field that already explains "why no trades today"
- **Stage(s) affected:** Intelligence Lab UI (`intelligence-lab/static/index.html`, `AVSHUNTER_sector_ui_patch.js`)
- **Business impact: HIGH.** This directly damages the objective's "internally consistent" bar at the exact point a human makes the go/no-go trust decision. 159/297 governed fields are never surfaced, including `readiness_label` (which already states, correctly, `EOD_PREP_COMPLETE_MORNING_VALIDATION_REQUIRED` for all 817 candidates today). Five specific UI panels — Convexity Score/Engine tab, Vetoes Fired, Entry Reason, Composite Score, AVOID/STAGED campaign stats — read legacy field names that don't exist in the current schema, silently showing 0/blank/"—" instead of real, correct, populated values one field-name away. No fabricated data was found; the defect is the opposite — a trader sees "the model has nothing to say" when it actually does.
- **Evidence:** Systematic field-name diff of all 297 `FINAL_BOOK_FIELDS` against both UI source files; targeted verification of 5 specific dead-reference panels against row 0 of `final_opportunity_book_20260829_100803.json` confirming the real field exists and is populated while the UI's referenced field name does not exist.
- **Prior status:** New finding — not addressed by `audits/intelligence_lab_audit_20260825/*`, which covered route/endpoint mechanics but not field-by-field UI/schema parity.
- **Suggested next investigation:** A focused UI field-audit (all 297 fields against all UI render paths) to produce a complete remediation list, prioritizing the 5 confirmed dead-reference panels and `readiness_label` first, since those directly misrepresent already-correct data at the trust-decision moment.

### 8. Two independent stale-metadata bugs corrupt data-quality flags as trustworthy audit signals
- **Stage(s) affected:** Package Build (`data_failure`/`dcv_valid`), Actuarial Cache/Query → Enrichment merge (`actuarial.deferred`)
- **Business impact: HIGH as a documentation/trust issue, though currently low as a behavioral one** (the one confirmed live consumer of each flag already defensively bypasses it). Both follow the identical pattern: a validation/placeholder snapshot is taken once, before a later stage populates real data, and is never refreshed. Any future consumer, dashboard, or manual QA pass that takes these fields at face value will draw false conclusions (e.g. "the entire universe has no price data," when 388/400 sampled packages actually do).
- **Evidence:** 400/400 sampled packages (100%) show `data_failure=True`; 388 of those 400 also contain real, populated OHLCV (`timeseries.ohlcv_daily`, typically 1,260 daily bars). `A.package.json["actuarial"]` carries both `"deferred": true` and fully real `enriched_by`/`sample_size`/`enriched_at` fields simultaneously.
- **Prior status:** New finding, verified at scale (400-package sample for one, full population read for the other).
- **Suggested next investigation:** Confirm whether any current or planned consumer (dashboards, QA scripts, external reporting) reads either flag without the defensive bypass logic the one known-safe consumer uses — if so, that consumer is currently drawing wrong conclusions today.

### 9. Upstream authority (morning_gate Check 0) blocks 72.5% of candidates before any other morning-side check matters
- **Stage(s) affected:** EIL (authority source) → morning_gate.py Check 0
- **Business impact: HIGH**, but root cause is Phase 9 (EIL/PSE), i.e. the same root cause as finding #1 — this is that finding's visible symptom one stage later, using the freshest available morning-side data (Aug 28, since today's run hasn't reached this stage).
- **Evidence:** `morning_validated_trades_20260828_094349.csv`: `check_upstream_authority_pass=FALSE` for 594/819 rows (72.5%), all `UPSTREAM_NOT_AUTHORIZED:NOT_AUTHORIZED`.
- **Prior status:** New quantification.
- **Suggested next investigation:** None beyond #1 — this is the same closed loop observed from the morning side.

---

## MEDIUM impact

### 10. `sample_confidence_bucket` is documented as a mandatory downstream gate but is not implemented as one anywhere
- **Stage(s) affected:** Vanguard → EIL/Trigger Layer/Final Decision Engine
- **Business impact: MEDIUM.** Currently inert (nothing reaches capital regardless of this gate's absence — see #1), but it means a documented safeguard against thin-sample actuarial matches reaching execution will not automatically fire if/when PSE is reactivated.
- **Evidence:** `vanguard/main.py:34-35` documents the requirement explicitly; grep of `execution_intelligence_runner.py`, `trigger_layer.py`, `final_decision_engine.py` for the field/values returns zero gating hits.
- **Prior status:** New finding.
- **Suggested next investigation:** If/when PSE reactivation is considered, confirm this gate is implemented before any capital-authority path goes live.

### 11. Bond macro CAUTION signal is silently dropped due to stale FRED yield-curve data
- **Stage(s) affected:** Macro Normalisation
- **Business impact: MEDIUM.** A real, deterministically-computed 55/100 `BOND_MACRO_CAUTION` score with an explicit staleness warning is nulled out in `macro_quant_packet.json` before packages ever see it — a genuine signal loss attributable to data freshness, not a code bug.
- **Evidence:** `dropbox/macro/bond_macro_state.json` (real score, staleness warning: yield curve 2 sessions old) vs. `macro_quant_packet.json` (`bond_macro_score: None`, `bond_macro_flag: "BOND_MACRO_PARTIAL_CONTEXT"`).
- **Prior status:** New finding.
- **Suggested next investigation:** Check how frequently the FRED yield-curve feed is actually stale across recent runs — if this is a persistent pattern rather than a one-off, the bond macro signal may be effectively unavailable most of the time.

### 12. Three independently-defined "actuarial state key" schemes exist for what should be one concept
- **Stage(s) affected:** Vanguard (`CORE_HASH_DIMENSIONS`, 9-dim), Actuarial Enrichment Pass Phase 8.5 (separate 9-dim key), Behaviour State Builder (`BEHAVIOUR_DIMS`, 7-dim)
- **Business impact: MEDIUM.** Increases audit surface and makes "how confident is the actuarial edge" harder to trace as a single lineage — a reader has to know which of three dimension sets produced which number.
- **Evidence:** Direct comparison of the three dimension-set constants across `vanguard/core/actuarial_core_v7.py`, `scripts/actuarial_enrichment_pass.py`, and `scripts/behaviour_state_builder.py`.
- **Prior status:** New finding.
- **Suggested next investigation:** Determine whether the three schemes are intentionally distinct (broad actuarial bucket vs. finer monetisation state vs. package-level match key, as one module's docstring suggests) or represent unintentional drift — if intentional, this is a documentation gap, not a design flaw.

### 13. Phase numbering does not track execution order anywhere in the pipeline
- **Stage(s) affected:** System-wide — Horizon Router ("Phase 1B" runs after Phase 8a), Trigger Layer ("Phase 8.6b" runs after Phase 9/10), "Phase 8b" used by two different unrelated stages, "Phase 11" meaning Execution Gate per code comments vs. "Diagnostics/Archive" per this pack's original phase-range brief
- **Business impact: MEDIUM.** Not a correctness defect — every case of number/order mismatch traced to a documented, deliberate reason. But it costs real audit/traceability time (this investigation itself had to resolve it independently in three of four agent scopes) and increases the risk of a future human or automated reasoning about the pipeline from phase numbers alone drawing wrong conclusions about execution order.
- **Evidence:** Direct code/comment citations in the main map's "Top-level finding" section.
- **Prior status:** Partially new — `docs/pipeline_map/06_MORNING.md`'s stale check-count claim is one symptom of this broader pattern.
- **Suggested next investigation:** Consider whether a single authoritative execution-order document (distinct from the phase-numbering scheme baked into log lines and code comments) would reduce future audit overhead — not a code change, a documentation one.

### 14. Governed-book field-count documentation drift (232 vs 297 vs 185)
- **Stage(s) affected:** `docs/INTELLIGENCE_LAB_FUNCTIONALITY_DATA_ROADMAP.md`
- **Business impact: MEDIUM.** Any human or GPT-agent guide built off the stale roadmap doc will misdescribe what a trader can actually see in the Lab today.
- **Evidence:** Live count 297 (two independent sources: schema definition and artefact); the doc's own cited reference run, opened directly, is actually 185 fields — the doc was internally inconsistent even at the time it was likely written.
- **Prior status:** CONTRADICTED (see prior-claims table in the main map).
- **Suggested next investigation:** Update the roadmap doc's field count and reference-run citation, or mark it explicitly superseded by this pack.

### 15. Prior `morning_gate.py` documentation is stale (5 checks, v1.2) — current is 8 checks, v1.3
- **Stage(s) affected:** `docs/pipeline_map/06_MORNING.md`
- **Business impact: MEDIUM.** Anyone relying on the old doc will misjudge current gate behavior and miss that Execution Gate now routes through the shared `morning_handoff_finalizer.py` rather than being called directly by the orchestrator (a real hardening improvement the old doc doesn't reflect).
- **Evidence:** Direct diff between the doc's described check set/call chain and current `morning_gate.py` (modified today).
- **Prior status:** CONTRADICTED.
- **Suggested next investigation:** Update or supersede the doc with this pack's findings.

### 16. Discovery's `win_probability` field is an unexplained arbitrary linear heuristic
- **Stage(s) affected:** Discovery
- **Business impact: MEDIUM.** The field name implies a calibrated statistic; the code is a fixed linear transform (`min(75, max(35, 40 + composite*0.25))`) with no stated empirical derivation — in contrast to the explicitly-cited, empirically-grounded state-prior-adjustment table immediately beside it in the same file. Whether any downstream consumer treats this as a real probability was not confirmed in scope.
- **Evidence:** Direct code read of `calculate_win_probability()`.
- **Prior status:** New finding.
- **Suggested next investigation:** Identify every consumer of the `win_probability` field and determine whether any of them weight it as if it were empirically calibrated — if so, that consumer is relying on an unverified assumption this pack's objective explicitly flags as a problem.

### 17. Wall Break Scorer's grade may not be consumed by any downstream code at all
- **Stage(s) affected:** Wall Break Scorer → EIL boundary
- **Business impact: MEDIUM**, separate from and additional to finding #1 (even setting aside the zeroed sizing valve, it's unclear WBS's grade is read anywhere).
- **Evidence:** Grep of `execution_intelligence_runner.py` for `wbs_grade`/`wbs_score` returns zero hits in sizing-assignment code.
- **Prior status:** New finding, explicitly flagged as unconfirmed rather than asserted.
- **Suggested next investigation:** Full-repo grep (beyond the sizing-assignment sites checked) for any consumer of `wbs_grade`/`wbs_score`, including Lab-display-only consumers, to determine if this is a genuine dead-end or an intentionally display-only field.

---

## LOW impact

### 18. "Phase 8b" label collision between Options Intelligence and the Catastrophe Gate no-op
- **Business impact: LOW** — minor log/code cross-referencing friction only, no confidence or correctness effect. **Evidence:** both modules self-label "Phase 8b" in comments/log lines. **Suggested next investigation:** none warranted at this impact level; a documentation fix if convenient.

### 19. Macro enrichment delta lookup has no staleness ceiling
- **Business impact: LOW**, currently inert — only one live delta file exists today. **Evidence:** `find_macro_enrichment_delta()` picks the newest-mtime matching file with no age check. **Suggested next investigation:** none warranted unless the operational pattern of maintaining delta files changes (e.g. if stale files start accumulating in the live directory rather than being archived).

---

## Register summary

| Impact | Count |
|---|---|
| High | 9 |
| Medium | 8 |
| Low | 2 |

The two highest-value findings for the business objective are **#1 (PSE hard-disabled system-wide)** and **#2 (macro_conviction is an uncalibrated LLM judgment)** — together they establish that even a perfect, fully-confident, fully-verified signal cannot generate a sized trade today (architectural, not a confidence problem), and that the master confidence input feeding everything else is itself the largest unverified assumption in the lineage (a confidence problem, but not one solvable by "raising the bar" on downstream scores). Any future work order narrowing scope to "raise confidence to resume trading" should explicitly decide whether it means (a) reversing PSE's retirement, (b) calibrating `macro_conviction`, or (c) something else — these are three different projects with different evidence requirements, and conflating them risks solving the wrong problem.
