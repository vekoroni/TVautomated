# Quant Product Blueprint V1: Opportunity Intelligence

18 September 2026 · prepared for ACK · **DRAFT for owner review. It is a design, and no code, configuration or test has been changed.**

| Item | Value |
|---|---|
| Scope decision | ACK, 18 Sep 2026: V1 is "Opportunity Intelligence" only |
| Position in the document authority | An implementation design. It sits below the specification (`Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` v1.1), method notes 01–07, the addendum and `Enhancements/decision_map/END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md`. The ten owner corrections of 18 Sep are folded in. Where a correction conflicts with a higher document, §9 lists the conflict for ACK to decide; this blueprint does not resolve it. |
| Working rule | CLAUDE.md rule 4 (ACK D1, 17 Sep 2026) applies: enhance existing modules in place, test first, one defect at a time. The strangler sequence in the pipeline map §7 is superseded by D1. |
| Evidence tags | **[M]** measured in this repository (file cited) · **[C]** read in code (file:line) · **[A]** assumption, to be confirmed |

---

## 1. Purpose and V1 scope

### 1.1 What V1 must deliver

Every session, a stable pipeline publishes a **tangible, non-empty daily ranked list of opportunities**. Each opportunity is one of:

| Expression | Scope in V1 |
|---|---|
| Long shares | In scope. The sleeve stays disabled until the share cost model (item C2) passes; §4 C5 |
| Long call | In scope (single leg) |
| Long put | In scope (single leg) |
| Short shares | Not in scope (open question Q4) |
| Debit verticals, spreads, short options | Not in scope |

Each published opportunity carries:

1. ticker, direction, expression and a stated **reason for the expression** (expected move against effective cost; §4 C4);
2. for options, **one matched contract** that passes the fact rules (§1.3), with its quote, spread, quote age state and delta-adjustment state;
3. **scenario values**: cautious, central and upside. Options are measured in return on premium. Shares are measured in return on notional. Each value is shown under the quoted and timed fill models;
4. the planned hold, the last usable session, the exit plan and the order instruction (limit, not market);
5. its rank, the size of the daily list, and the authority label *"Decision support · SHADOW · no capital authority"*.

**Every candidate is recorded, not only the issued tickets.** The daily record includes the candidates that were valued but ranked below the cap, the candidates excluded for a fact (with the reason code), and the universe counts above them. The outcome scorer then marks the not-issued candidates by the same exit rules as the tickets (item B1). This is the full denominator that blocker 11 says competing products omit (`Enhancements/assessment/MONETISATION_BLOCKERS_20260918.md` §11).

**"Non-empty"** means the list contains at least one issued opportunity whenever at least one candidate passes the fact rules. A day on which nothing passes is published as an explicit `EMPTY_DAY` record, with the count excluded at each fact rule. It is never a silent absence.

**"Stable"** means the list is produced on every XNYS session on which the evening run completed, even if an advisory legacy stage fails (item A5). Run health reports the funnel counts (§6).

### 1.2 What V1 is not

V1 does not claim a profitable edge. The measured position [M] is:

- The best-valued fifth of candidates still lost 29% of premium at quoted fills, and about 17% at timed fills (`Enhancements/backtest/SIGNAL_TICKET_BACKTEST_20260917.md`, `fill_model_study_summary.json`: top cautious quintile −26.7% quoted, −16.7% timed, −11.0% mid).
- Direction has no demonstrated skill (blocker 1).

Items A1–A6 stop the pipeline destroying value and remove the empty days. Items C1–C5 are where a small positive edge could come from. Every item is judged by the outcome scorer.

### 1.3 Hard exclusions: facts only (R11, owner correction 5)

A candidate or contract may be excluded **only** for one of the facts below. Every forecast only ranks: the cautious value, Wyckoff, momentum, the composite, GEX, macro and flow.

| Fact | Rule | Governed key (existing or new) |
|---|---|---|
| Integrity | Clean price history (DQ-12 state `INTACT`) | `outcome.signal.required_price_history_state` (exists) |
| Integrity | No corporate-action contamination inside the look-back | `opportunity.integrity.corporate_action_lookback_sessions` (new, item A7) |
| Eligibility | Price, dollar volume, bar history | `opportunity.cross_section.min_price_usd`, `…min_median_dollar_volume_usd`, `…min_history_sessions` (new) |
| Tradeability | Two-sided executable quote (`execution_viability_state = EXECUTABLE_QUOTE`) | `domain/long_option_execution.py` viability; spread limit below |
| Tradeability | Entry spread ≤ limit, measured as (ask − bid) / mid | `outcome.signal.max_entry_spread_fraction` = 0.10 (exists) |
| Tradeability | The contract outlives the planned hold | `outcome.signal.min_dte_cover` = 1.5 and `outcome.signal.min_contract_dte_days` = 21 (both exist) |
| Tradeability | Moneyness limit | `outcome.signal.max_out_of_the_money` = 0.05 (exists); `opportunity.selector.max_in_the_money` (new) |
| Thesis state | Target already reached, or thesis invalidated before issue (`signals.thesis_position`) | none (a fact about the published thesis) |

### 1.4 Deferred (out of V1)

**Deferred:** capital authority, position sizing, trust gates G1–G4 for authority, and power calculations. The existing track-record verdict in `signals.evaluate` keeps running as a report only.

Also deferred, each with its reason given in §8:

- debit verticals and short options;
- short shares (Q4);
- the event (earnings) sleeve as a ranking input (§9 C6; data gap Q3);
- far out-of-the-money or long-dated convexity (no chains beyond 60 DTE; Q1);
- trade-level flow signals (Q2);
- machine-learning models (challenger protocol only, §4 R6);
- universe restoration (Q5).

---

## 2. Target V1 flow

```text
EVENING (python intelligent_orchestrator.py --evening; stage numbers from intelligent_orchestrator.py)
─────────────────────────────────────────────────────────────────────────────────────────────────
 [0]  Session authority → evidence session (point-in-time clock)                         KEEP
 [2]  Universe (data/universe/polygon_liquid_universe.csv, 3,320 tickers)                 KEEP (Q5)
 [11] Discovery → thesis rows: direction, structural invalidation, structural target      KEEP (asset)
 [16] Vanguard / packages (legacy direction governance)                                   KEEP (not read by V1 rank)
 [19] Options Intelligence ── chain parse (KEEP) ── contract selector (CHANGE A2/A3)
        reads  opportunity.planned_hold_sessions + fact keys (one owner per fact)
        writes options_intelligence_{run}.csv (+ bounded set, R5)
 [21] Horizon router ─ display only (QUARANTINE); never drives DTE or hold
 [35] EIL ─ advisory; its failure no longer skips [37]/[38] (A5)
 [37] Layer 3 HAR-RV forecast at the planned-hold horizon, DQ-12 state                   CHANGE (A2)
 [37b] NEW  Cross-sectional composite (avshunter/cross_section) over the eligible universe
        → cross_section_scores_{run}.csv: composite z, decile, μ_H ± CI (bps), β_60   (C1, SHADOW)
 [38] Path valuation (empirical_option_ev.py) on ONE path set per ticker:
        planned hold (A2) · exit rule without an underlying stop in the hold (A4)
        · drift μ_H (C3, switchable) · option and share values · quoted / timed / mid (B2)
        · option breakeven drift, the expression hurdle (C4)
        → emp_* columns: cautious / central / upside per expression and fill model
 [42] EOD candidate engine, [46] lab_control Lab book ─ legacy; GEX authority off (A6)
 [51] C12 outcome scorer: ingest · score · expressions · signal-scores
        · candidate-scores (B1) · beta split (B4) · fill models (B2)       → outcome_scoring.sqlite
 [51b] Capture list for open candidates → the next evening's chain capture (B3)

MORNING (python intelligent_orchestrator.py --morning, ~15 min after the open)
─────────────────────────────────────────────────────────────────────────────────────────────────
 [M4] morning_gate.py: live spot, live contract quote, IV, delta, viability             KEEP (facts only are read)
 [M5] morning_handoff_finalizer / execution_gate / lab_control ─ legacy Lab book          KEEP; GEX multiplier off (A6)
 [M6] NEW step: python -m avshunter.c12_outcome signals                                    (B5)
        prepare (facts) → revalue at issue premium → decide (facts) → rank → daily cap
        → signal_tickets + signal_candidates (every candidate, values, rank, reason)
        → signals/signal_tickets_{run}_{session}.csv/.md, opportunity_funnel_{…}.json

AFTER EVERY EVENING RUN
─────────────────────────────────────────────────────────────────────────────────────────────────
 C12 scorer marks tickets AND not-issued candidates (same exit rule, bid/timed/mid)
 → Enhancements/outcomes/<session>/ report → Intelligence Lab "Opportunities" tab (read-only, B6)
```

Data sources in the flow:

| Data | Source | Notes |
|---|---|---|
| Daily bars | `data/canonical/historical_prices.sqlite` | Read by `avshunter/c12_outcome/adapters/prices.py` |
| Chains and expression marks | `data/phantom/phantom_history.db` `chain_snapshots` | Daily quote dates from 2021-05-28 to 2026-09-17, 279 dates in total [M, queried read-only] |
| Intraday bars | `data/canonical/market_observations/intraday_bar/` | — |
| Scoring store | `data/canonical/outcome_scoring.sqlite` | — |
| Configuration | `config/registry/*.json` via `avshunter.config.adapters.load_registry().resolve(session)`, and `config/governed_constants_v1.json` | — |

---

## 3. Module table

The decisions are KEEP (used as is), CHANGE (fix in place), RETIRE (remove from the pipeline), and QUARANTINE (kept for display or research only, with no influence on any V1 exclusion, value or rank).

### 3.1 Orchestration and data

| Module / function | Decision | Reason (evidence) | V1 responsibility |
|---|---|---|---|
| `intelligent_orchestrator.py` `evening_workflow` (L4823) | CHANGE | Layer 3 and path valuation run only when EIL succeeds (L5911–5923 [C]), so a failed advisory stage removes the valuation the tickets need. The WS2 trigger spine raises and fails the whole run (L5907–5909 [C]) | Run the V1 path independently of advisory stages (A5). Insert stage 37b (C1) and the open-candidate capture list (B3) |
| `intelligent_orchestrator.py` `premarket_workflow` (L7015) | CHANGE | Tickets are issued only by a separate manual command (`avshunter/c12_outcome/__main__.py:56–64` [C]), so the daily list depends on the operator remembering it | Add step M6 (issue the list, B5); non-blocking; writes the funnel |
| `--plan-only` dispatch (L7503, L7604) | KEEP | Changes nothing on disk [C] | Pre-run check, as CLAUDE.md requires |
| Session authority (`orchestrator/session_authority_adapter.py`, stage 0) | KEEP | Point-in-time evidence session | Clock for every V1 record |
| Universe consumer (`load_scanner_manifest` L613, `build_augmented_universe` L758) | KEEP | 3,320 tickers; 6,500 is only a warning level (L4826, L7465 [C]); scanner manifest from 20 Aug is ignored as stale | Unchanged in V1 (Q5) |
| Pre-flight `run_preflight_checks` (L1189) | KEEP | Hard stop below 1,000 tickers is an integrity fact | — |
| Phase 2 quality validation (L1870) | KEEP (flag) | Hard stop when candidates are < 15% of the universe [C]. This is a run-level integrity rule, but it is a stability risk | Reported in run health; review if it stops a run |
| Canonical → Phantom projection (stage 20, `canonical_data/phantom_option_projection.py`) | CHANGE | Exits could not be marked on 325 backtest trades, and 5,633 positions were open at the data edge (`SIGNAL_TICKET_BACKTEST_20260917.md` [M]) | Also capture chains for tickers with open candidates or tickets (B3) |
| `garch_runner.py` + `layer3_forward_variance.py` `compute_forward_variance` (L584) | CHANGE | The HAR-RV forecast is averaged over a fixed 20 sessions (L642 `horizon=20` [C]) while the plan holds for a different length. DQ-12 states are produced here (L95, 185, 555 [C]) | Forecast at `opportunity.planned_hold_sessions` (A2); DQ-12 unchanged |
| `config/registry/c12_outcome.json` | CHANGE | Holds the ticket rules [C] | New versions of `outcome.signal.*` (A1, B1) |
| New `config/registry/opportunity.json` (prefix `opportunity.`) | NEW | No existing owner for the horizon, cost, cross-section and exit-policy keys | One owner for each V1 product rule; locked in `config/registry/LOCK.json` |
| `config/governed_constants_v1.json` | KEEP | `empirical_path_valuation`, `option_quote_feed` and `price_history_integrity` are already governed [C] | Unchanged; legacy readers keep reading it |

### 3.2 Thesis, direction and legacy decision layers

| Module / function | Decision | Reason (evidence) | V1 responsibility |
|---|---|---|---|
| `avshunter_discovery_ULTIMATE.py` (stage 11) | KEEP | Source of thesis rows and structural levels. Its direction has no measured skill (blocker 1) | Candidate generator for the option sleeve; its direction is recorded as `direction_source = LEGACY_THESIS` |
| `assign_discovery_horizon` (`avshunter_discovery_ULTIMATE.py:2236–2262`) | QUARANTINE | One of three competing horizon producers (blocker 4) | Display only |
| `vanguard/layer2_statistical/actuarial_query.py:1128` `recommended_hold_days` | QUARANTINE | The value is `20` whenever P(+10%) ≤ 0.5 [C]. That is a default posing as a measurement (R1). It is read as the hold by the selector (`scripts/avshunter_options_intelligence.py:4094, 4224`), path valuation (`empirical_option_ev.py:443`) and tickets (`signals.py:250`) | Display only; replaced by the canonical hold (A2) |
| `macro_horizon_router.py` `route_signals_by_horizon` (stage 21) | QUARANTINE | 6_10d on 1,237 of 1,498 rows in run 20260917_214854 [M]. It drops NOT_SCOPED rows (L1441–1456 [C]) | Display only; never an input to DTE, hold or membership of the V1 path |
| Macro stages (sector alignment, normaliser, bond, USMI, enrichment, `scripts/macro_quant_packet.py`) | QUARANTINE | Display only by ACK decision (CLAUDE.md rule 6) | Lab macro panel only |
| Vanguard pipeline (`scripts/run_vanguard_from_packages.py`), packages | KEEP (legacy) | Needed for the legacy book; verdicts carry macro floors (pipeline map S8) | Not read by V1 exclusions, values or rank |
| `trigger_layer` (stage 28), SuperBrain passthrough (29), FIX-ACTUARIAL-SEQ (33) | QUARANTINE | The trigger spine can fail the run (L5907–5909); 62% of rows are "GO" with freshness that can never fire (pipeline map S12) | No V1 input; A5 isolates the V1 path from its failure |
| Catastrophe gate (stage 31) | RETIRE | No-op since Sprint 2 [C, orchestrator L3843] | Remove the call |
| `execution_intelligence_runner.py` EIL (stage 35) | QUARANTINE | Synthetic GEX map (GEX-D7); 73% BLOCKED on end-of-day quotes (pipeline map S12) | No V1 input |
| `wall_break_scorer.py` (stage 32) | QUARANTINE | Built on the defective flip and on OI walls (GEX-D1, D3, D4); feeds the EOD engine at 15% | No V1 input (A6) |
| `eod_candidate_engine.py` (stage 42), `scripts/exit_rules_engine.py` | KEEP (legacy) | Legacy Lab statuses and exit plan | Tickets carry their own exit plan; WBS weight off (A6) |
| `avshunter_exit_engine.py` L333–346 | QUARANTINE (GEX branch) | EMERGENCY_EXIT when a call wall sits below spot (GEX-D4) | GEX branch off (A6) |
| `catalyst_truth_engine.py`, `earnings_calendar_enricher.py` | KEEP (display) | Earnings come from a Polygon snapshot field that method note 04 lists as unreliable; no point-in-time calendar exists (blocker 7) | Event flag shown on each opportunity; no influence (§9 C6) |
| `mcmillan_advisory_layer.py`, `scripts/core_intel_exporter.py`, `scripts/phantom_engine.py`, DOI-11 | QUARANTINE | Advisory or off | None |
| `scripts/run_ev3_shadow_phase.py`, `scripts/apply_ev3_authority.py`, `vanguard/ev_engine_v2.py` | QUARANTINE | EV3 authority is retired; legacy EV v2 is not an expected value (CLAUDE.md rule 5) | Never shown as EV in the V1 surface |
| `avshunter_trade_journal.py` position lock (stage 18) | KEEP | Fact: an open trade on the ticker | Reported on the candidate |

### 3.3 Options, valuation and execution

| Module / function | Decision | Reason (evidence) | V1 responsibility |
|---|---|---|---|
| `scripts/avshunter_options_intelligence.py` chain parsing, quotes, provider greeks | KEEP | Bid, ask, IV, strike, expiry and DTE recompute exactly from the raw chain (pipeline map S10) | Source of contract facts |
| `DTE_CONFIG` (L1215–1219), `normalise_horizon_key` (L1237), `governed_dte_config` (L1263), `HORIZON_PLANNED_HOLD_SESSIONS` (L1255) | CHANGE | The DTE window follows the horizon bucket (1_5d 7–21, 6_10d 21–35, 11_20d 35–60), while the theta score and valuation use the Layer 2 hold [C]. Tickets held contracts covering a median 0.54 of their plan, and the expiry cap was the most common exit (blocker 4 [M]) | The DTE window comes from the canonical hold and the fact keys (A2, A3) |
| `select_best_contract` (L4555–4794) | CHANGE | Its hard delta band 0.20–0.75, target reachability filter and weighted Greek score pre-select contracts before valuation. The route taxonomy rejects `ESTIMATED_R_LT_1` (89 rows, a forecast veto) and `NO_CONTRACT_PASSED_QUALITY_GATES` (838 rows) in run 20260917_214854 [M, `contract_rejection_log`]. Its spread limit (25%, L1187/1306) differs from the ticket limit (10%) | Fact-only filters read from the ticket keys; deterministic matched contract (A3); bounded set output (R5) |
| `compute_gex` (L2996), `compute_oi_walls` (L3155), gamma island / velocity | QUARANTINE | Ten defects, including a flip that is median 22.3% from spot against 5.5% correct (`Enhancements/gex/GEX_INVESTIGATION_20260914_214012.md` [M]) | Research display only, labelled; no consumer in V1 (A6) |
| IV-vs-HV score adjustments (L5898–5967), `options_score`, routes | QUARANTINE | Hand-set score points on a forecast (R11) | Display; the IV/forecast ratio is published by valuation instead (C4) |
| `empirical_option_ev.py` `compute_path_expression_ev` (L639), `_simulate_path_exits` (L480), `_option_result` (L558), `abdi_ranaldo_spread` (L606), `expression_preference` (L628) | CHANGE | Zero drift (L368 [C]). Paths exit at the underlying stop (L536–549). Hold comes from Layer 2 (L443). A share is valued only when an option contract exists: 977 of 1,498 rows are `NO_SELECTED_CONTRACT`, so their shares are not valued either [M, run 20260917_214854]. Share return is per unit of risk to the stop. The Abdi-Ranaldo spread is 0 on 14% of rows [M] | The single path valuation: canonical hold (A2), exit without a stop (A4), three fill models (B2), shares for every eligible ticker per notional (C3), drift switch (C3), breakeven hurdle (C4) |
| `compute_empirical_option_ev` (L205–361, older percentile EV) | QUARANTINE | Superseded by the path valuation; `VOL_DIVERGENCE_BLOCK` is a forecast veto (L264 [C]) | Not read by V1 |
| `domain/long_option_execution.py` `evaluate_execution_viability` (L165) | KEEP | A fact function: quote present, not crossed, timestamp, freshness with a disclosed 900 s delay, spread bands [C] | Supplies `EXECUTABLE_QUOTE`; the ticket spread key governs tickets |
| `morning_gate.py` `_fetch_live_price` (L797), `_fetch_live_contract` (L834), `_try_live_repair_alternatives` (L1254) | KEEP | Live facts for the morning | Fact provider for step M6 |
| `morning_gate.py` decision ladder (`run_gate` L2103, ladder L2583–2725) | QUARANTINE (for V1) | Upstream authority fails → BLOCK (L2583). Run 20260916: 1,165 BLOCK, 291 FLAG, 20 GO [M] | Legacy Lab only; its verdict is never read by V1 |
| `execution_gate.py` `execution_gate` (L201) | KEEP (legacy) with GEX off | 0.75× size when spot is above the defective flip (L389–399 [C]), which applies to 81.6% of rows (GEX investigation). The OLM disposition returns before `UPSTREAM_BLOCK`, turning 819 Morning BLOCK rows into review labels in run 20260916 [M] | GEX multiplier off (A6). The ordering defect is legacy-only and outside V1 (noted) |
| `morning_handoff_finalizer.py` `finalize_morning_handoff` (L706) | KEEP | Legacy handoff and Lab book | Step M6 runs after it |
| `contracts/lab_control.py` `opportunity_book_row` (L2756), `_enforce_olm_lab_guard` (L2653), `build_final_opportunity_book` (L3442) | KEEP (legacy) | 1,498 rows → 738 CONTRACT_REPAIR, 594 MANUAL_REVIEW, 166 BLOCK (all `INVALIDATION_MISSING`), 0 actionable [M]. The Lab target falls back to `wbs__wall_price` (L2872, GEX investigation) | V1 no longer reads `final_action` (A1); the GEX target fallback is removed (A6) |

### 3.4 Measurement, tickets and presentation

| Module / function | Decision | Reason (evidence) | V1 responsibility |
|---|---|---|---|
| `avshunter/c12_outcome/signals.py` `prepare` (L228) | CHANGE | Rejects `FINAL_ACTION_BLOCKED` using the legacy verdicts `["BLOCK","CONTRACT_REPAIR"]` (L237, registry `outcome.signal.blocked_final_actions`), which carry 904 of 1,498 rows in the latest book [M]. Hold comes from Layer 2 (L250). A missing target rejects the candidate (L251) | Fact checks only (A1); canonical hold (A2); `target_state = NONE` is allowed (A4) |
| `signals.decide` (L307), `rank_tickets` (L369), `apply_daily_cap` (L385) | CHANGE (in progress) | **Fix 1, "rank, don't gate", is being implemented by the main session** (uncommitted: `outcome.signal.max_entry_spread_fraction`, `outcome.signal.max_tickets_per_session` = 5, `approval_id ACK-20260918-RANK-NOT-GATE`) | Unchanged by this blueprint; C4 and C5 build on it |
| `signals.plan_exit` (L402) | CHANGE | Exits at the first touch of the stop (L414–416). Removing the underlying stop inside the hold gains +2.9 points, t = 3.21, on 638 paired trades (`EXIT_RULE_STUDY_20260917.md` [M]) | New exit policy (A4) |
| `signals.mark_signal` (L438) | CHANGE | Options are marked at the bid only | Quoted, timed and mid marks (B2) |
| `signals.evaluate` (L470) | KEEP | Trust-gate report | Report only; authority is deferred |
| `signal_service.issue_signals` (L66) | CHANGE | Records issued tickets in `signal_tickets`, but only a reason string for the rest (`signal_rejections`) | Record every candidate with its values and rank (B1); share sleeve (C5); funnel file (B5) |
| `signal_service.score_signals` (L171) | CHANGE | Scores tickets only | Score every recorded candidate (B1) |
| `avshunter/c12_outcome/service.py` `ingest` (L82), `score` (L123), `score_expressions` (L306), `build_report` (L538) | KEEP + CHANGE | Scoring works (19,910 prediction records, 17,164 option marks, blocker 10 [M]) | Add a beta split (B4), fill models (B2) and a candidate-outcome report section (B1) |
| `service.track_hypotheses`, `hypotheses.py` (H9R), `base_rate.py`, `conditions.py` | KEEP | Pre-registered forward tests | Unchanged |
| `avshunter/c12_outcome/adapters/chains.py` `ChainQuotes` | CHANGE | Bid only for exit marks | Also read ask and mid (B2) |
| New `avshunter/cross_section/` | NEW | No existing owner. The research exists only as `Enhancements/research/drift_calibration.py` | Composite score, decile calibration and μ_H with an interval (C1) |
| `intelligence-lab/intelligence_lab.py` | CHANGE | Never reads `avshunter/c12_outcome`; shows the legacy book only [C, agent map §5] | Read-only "Opportunities" tab and endpoints (B6) |
| `Enhancements/backtest/*.py` harness | KEEP | Calls the shipped `signals` and `empirical_option_ev` code | Measurement protocol for every item (§4) |
| `Enhancements/research/drift_calibration.py` | KEEP (research) | Pre-registered study | Imports the production module after C1, so there is one implementation |

---

## 4. Item specifications

Every item follows CLAUDE.md rule 4 in the same order:

1. characterise (pin the legacy behaviour);
2. write a failing business-rule test in domain language;
3. make the minimal change;
4. accept it against reality with the outcome scorer, on history (the harness) and on forward sessions.

Test commands:

- Rebuild-package tests: `venv\Scripts\python.exe -m pytest tests_rebuild -q -p no:cacheprovider --basetemp=%TEMP%\avs_rb`
- Legacy-module tests: one file per process under `tests/`, with `--basetemp=%TEMP%\avs_pt`

**Harness conventions for every measurement.** The harness is `Enhancements/backtest/signal_ticket_backtest.py`: 8,950 valued candidates over 9 sessions (31 Aug–16 Sep 2026), point in time. Its follow-on studies are `exit_rule_study.py` and `fill_model_study.py`. Every measurement follows these rules:

- **Pre-registration.** Write the metric and pass threshold in the item's evidence file before running.
- **Scopes.** Report tickets, the top cautious quintile and all candidates.
- **Fill models.** Report quoted, timed (0.30) and mid.
- **Paired comparisons.** Pair on identical trades wherever a rule changes an exit.
- **Uncertainty.** Cluster t-statistics by issue session.
- **Honesty about the sample.** The harness is one regime of two weeks (SPY −2.0%, IWM −4.0%). Every report says so.
- **Forward acceptance.** The C12 scorer on forward sessions must show the targeted metric moving in the same direction. Authority is not granted in V1.

### A0. Rank, don't gate for tickets (fix 1): in progress, not redesigned here

Being implemented by the main session. The rules are fact checks plus a ranked daily cap of the top N by cautious value (`signals.decide`, `apply_daily_cap`, registry `outcome.signal.max_tickets_per_session` = 5, `outcome.signal.max_entry_spread_fraction` = 0.10). Evidence: the cautious > 0 gate kept 20 of 2,992 trades and rejected every large winner, while cautious value as a ranking correlates 0.44 with realised return (blocker 2 [M]). Every later item assumes A0 has shipped.

### A1. The ticket path reads facts, not legacy verdicts

- **Root cause (for approval).** `signals.prepare` rejects any row whose legacy Lab `final_action` is BLOCK or CONTRACT_REPAIR (L237). Those labels come from the OLM and invalidation guards in `contracts/lab_control.py` (L2653–2712, L3406–3430) and the execution-gate ladder. They mix facts (no contract, missing invalidation) with forecasts and ordering defects (blocker 9: 0 actionable of 1,498). A forecast therefore vetoes candidates through a side door, against R11.
- **Specification.** Remove the dependency on `final_action`. Each underlying fact is checked directly, and each already has a named rejection in `prepare`/`decide`:
  - no contract → `CONTRACT_UNPARSEABLE` or `OPTION_NOT_EXECUTABLE`;
  - missing invalidation → `STOP_OR_TARGET_UNDEFINED`, renamed `INVALIDATION_UNDEFINED`;
  - direction not CALL or PUT → `DIRECTION_NOT_CALL_OR_PUT`;
  - DQ-12 → `PRICE_HISTORY_NOT_INTACT`.
- **Configuration.** A new version of `outcome.signal.blocked_final_actions` with the value `[]`. The key is kept so replay of old versions is exact (spec Appendix B).
- **Inputs.** `final_opportunity_book_{run}.csv` (ticker, final_direction, pipeline_mode), `morning_validated_trades_{run}.csv` (live_price, live_high, live_low, live_contract_*, execution_viability_state, selected_quote_timestamp_utc), and `options_intelligence_{run}.csv` (invalidation_spot, structural_target, contract_*, l3_*, emp_*).
- **Outputs.** Unchanged ticket fields; rejection reasons are now facts only.
- **Acceptance.**
  - Failing test `test_candidate_with_legacy_review_label_but_executable_contract_is_ranked`: *"a candidate whose legacy Lab action is MANUAL_REVIEW or CONTRACT_REPAIR, whose contract has an executable two-sided quote inside the ticket spread limit and outlives the plan, is valued and ranked."*
  - Characterisation test pinning today's `FINAL_ACTION_BLOCKED` behaviour under the old key version.
- **Measurement.** Harness: count of candidates reaching `decide` and the top-5 mean or median return, before and after. Forward: rejection mix in `signal_rejections`; no `FINAL_ACTION_BLOCKED` after the version date.
- **Insertion.** Morning step M6 (`signal_service.issue_signals`).

### A2. One canonical planned holding horizon

- **Root cause (owner-accepted, correction 6).** Three components disagree about how long a trade lasts [C, M]:

  | Component | What it assumes | Source |
  |---|---|---|
  | Horizon bucket | Drives the DTE window (`DTE_CONFIG`) | Discovery and router; 6_10d on 1,237 rows |
  | Theta score, path valuation and ticket hold | `layer2__recommended_hold_days`; median 20, as a fallback | L4224, `empirical_option_ev.py:443`, `signals.py:250` |
  | Layer 3 forecast | Averaged over 20 sessions | L642 |

  As a result, contracts covered a median 0.54 of the plan, and the expiry cap ended 364–515 of about 1,000 exits (blocker 4).
- **Specification.**
  - One governed value, `opportunity.planned_hold_sessions` (XNYS sessions), is used by every consumer: selector DTE window, Layer 3 forecast horizon, path-valuation hold, ticket hold, exit rule and scorer.
  - The fact rule "contract outlives the plan" stays as it is: `dte_calendar_days ≥ max(outcome.signal.min_contract_dte_days, outcome.signal.min_dte_cover × planned_hold_sessions × 7/5)`.
  - Each candidate records `planned_hold_sessions` and `planned_hold_source = "opportunity.planned_hold_sessions@<version>"`.
  - Legacy hold fields stay in the row as display fields, renamed in the V1 surface to `legacy_*`.
- **Provisional value [A]: 10 sessions.** It is confirmed or replaced by study R4 before A3 ships. The reasons:
  - The composite's gross top-minus-bottom spread rises from 5 to 10 sessions (30–32 bps to 41–54 bps across the three liquidity cuts, `drift_calibration_summary*.json` [M]).
  - The no-stop exit held a median of 7 sessions (`EXIT_RULE_STUDY` [M]).
  - At 10 sessions the cover rule needs at least 21 calendar days, which falls inside the captured 7–60 DTE range (`market_data.chain.from_offset` 7, `to_offset` 60 in `config/registry/c1_market_data.json`).
- **Configuration.** `opportunity.planned_hold_sessions` (INTEGER, sessions, PROVISIONAL, evidence R4). Legacy modules read it through `avshunter.config.adapters.load_registry().resolve(evidence_session)`, so there is one owner.
- **Inputs and outputs.** Adds `planned_hold_sessions`, `planned_hold_source`, and `l3_forecast_horizon_sessions` (Layer 3 output) to `options_intelligence_{run}.csv` and the ticket and candidate records.
- **Acceptance.**
  - Failing test `test_one_planned_hold_drives_contract_valuation_ticket_and_scoring`: *"for any candidate, the hold used to choose the contract, to value it, to issue the ticket and to score it is the same governed number."*
  - `test_layer3_forecast_horizon_equals_planned_hold`.
  - Characterisation tests pin the three current values.
- **Measurement.** Harness re-run at the chosen H: share of exits at `CONTRACT_LAST_USABLE` (target: well below 364/1,009) and paired mean return. Forward: the exit-reason mix in `signal_outcomes`.
- **Insertion.** Evening stages 19, 37 and 38; morning M6; scorer at stage 51.

### A3. Fact-only contract selection with a deterministic match

- **Root cause (for approval).** `select_best_contract` excludes contracts on forecasts (target reachability, and `ESTIMATED_R_LT_1` at the route level) and on a hard delta band. It picks by a hand-weighted score. It applies a 25% spread limit while tickets require 10%. So 838 rows found no contract at all, and a contract chosen at 20% spread is later rejected by the ticket rule even when a 9% contract existed [C, M].
- **Specification.** Contracts are generated in the order below; the delta band, reachability filter and weighted score are removed.
  1. **Side.** CALL for BULL, PUT for BEAR.
  2. **Expiries.**
     - The lower bound is the A2 cover rule.
     - The upper bound is `opportunity.selector.max_dte_days`, taken from capture: `to_offset` is 60.
  3. **Strikes.** Moneyness m = sign · (spot − K)/spot, kept within `[−outcome.signal.max_out_of_the_money, +opportunity.selector.max_in_the_money]`.
  4. **Fact filters.**
     - Two-sided quote: bid > 0, ask ≥ bid, not crossed.
     - `spread_fraction_mid ≤ outcome.signal.max_entry_spread_fraction`, the same key as tickets.
     - Open interest ≥ `market_data.chain.min_open_interest`.
  5. **Matched contract.** Choose deterministically by:
     - smallest |m|, then
     - smallest DTE that satisfies the cover rule (least premium for the plan), then
     - smallest spread fraction, then
     - OCC symbol.

  R5 later replaces step 5 with "highest cautious value in the bounded set". Every fact exclusion is recorded with a reason code in `contract_rejection_log_{run}.csv`.
- **Configuration.**
  - Existing keys, now read by the selector: `outcome.signal.max_out_of_the_money`, `outcome.signal.max_entry_spread_fraction`, `outcome.signal.min_dte_cover`, `outcome.signal.min_contract_dte_days`.
  - New keys: `opportunity.selector.max_in_the_money` (fraction; provisional 0.10 [A]) and `opportunity.selector.max_dte_days` (calendar days; 60).
  - `DTE_CONFIG`, `MAX_SPREAD_PCT` and `HORIZON_PLANNED_HOLD_SESSIONS` stop being read on the V1 path.
- **Outputs.** The existing contract columns (`contract_occ_symbol`, `contract_strike`, `contract_expiry`, `contract_dte`, `contract_bid`, `contract_ask`, `contract_mid`, `contract_iv`, `contract_delta`, `contract_spread_pct`), plus:
  - `contract_moneyness`;
  - `contract_dte_cover` (DTE ÷ planned hold in calendar days);
  - `contract_selection_rule_version`;
  - `bounded_set_size`.
- **Acceptance.**
  - `test_selected_contract_outlives_the_planned_hold`.
  - `test_no_forecast_removes_a_contract_before_valuation`: a contract with a low estimated R, or a target short of the strike, is still selectable.
  - `test_selector_and_ticket_share_one_spread_limit`.
  - `test_matched_contract_is_the_nearest_the_money_that_passes_the_facts`.
- **Measurement.**
  - Per run: share of thesis rows with a contract (521 of 1,498 today), median spread and median DTE cover.
  - Harness: the far-OTM study shows that near-the-money bands lose least (`otm_tail_study_summary.json` [M]; Boyer-Vorkink), so the paired return must not fall.
  - Forward: `CONTRACT_EXPIRES_BEFORE_PLAN` rejections fall to near zero.
- **Insertion.** Evening stage 19.

### A4. Exit policy without an underlying stop inside the planned hold

- **Root cause (owner-accepted, correction 7).** A stop 0.63 expected moves away is reached by noise: 20 of 21 tickets stopped out at a median of 2 sessions. Removing it gains +2.9 points (t = 3.21, 638 paired trades) and lifts the profitable share from 30.7% to 36.5%. The premium already caps the loss (`EXIT_RULE_STUDY_20260917.md` [M]).
- **Specification (ticket exit, first event in this order).** The path valuation must use the same rule, so that the value predicts what is scored.

  | # | Exit | Rule |
  |---|---|---|
  | 1 | `DATA_OR_CONTRACT_FAILURE` | No quote for 2 consecutive sessions, the contract is halted, or a corporate action affects the contract. The position is marked `MARK_UNAVAILABLE`, never substituted |
  | 2 | `THESIS_INVALIDATED` | A close beyond the structural invalidation level, counted only when that level is at least `opportunity.exit.invalidation_min_expected_moves` (provisional 1.5) expected moves away over the hold at issue. Otherwise it is recorded as `INVALIDATION_INSIDE_NOISE` and not used inside the hold. At 1.5 moves this rule was identical to no stop in the sample (6 stops in 652 exits, `exit_rule_study_top_quintile_summary.json` [M]). §9 C3 asks ACK to confirm the definition |
  | 3 | `TARGET` | Touch of the structural target. A 3R or expected-move target is treated as `target_state = NONE` [A: the target source field must be verified in `options_intelligence_*.csv`] |
  | 4 | `PLANNED_HOLD_COMPLETE` | At `planned_hold_sessions` |
  | 5 | `DTE_SAFETY` | At `last_usable_session` = expiry minus `outcome.contract_exit_buffer` (2) sessions. Under A2/A3 this should rarely come before the hold |
  | 6 | `EVENT_COMPLETE` | Recorded as a display flag only in V1 (§9 C6) |

  **Order instruction.** Every exit is a limit order at mid − `opportunity.execution.limit_offset_fraction` (0.30) × half-spread, repriced each session. It is never a market sell into a quote wider than `opportunity.execution.max_exit_spread_fraction` (provisional 0.25 [A]) except at `DTE_SAFETY`. This follows the evidence:
  - median exit spread of 60.9% across all exits (`fill_model_study_summary.json` [M]);
  - 71% on stop exits (owner figure; not found in a repository file).
- **Configuration.**
  - New: `opportunity.exit.invalidation_min_expected_moves`, `opportunity.exit.policy_version`, `opportunity.execution.limit_offset_fraction`, `opportunity.execution.max_exit_spread_fraction`.
  - Existing: `outcome.contract_exit_buffer`.
- **Inputs.** Ticket fields `stop_spot`, `target_spot`, `hold_sessions`, `last_usable_session` and `reference_spot`; the issue-time `σ_H` (new ticket field `expected_move_hold_fraction` = forecast vol × √(H/252)); daily bars.
- **Outputs.**
  - `SignalExit.reason` takes the new vocabulary above.
  - New ticket fields: `invalidation_distance_expected_moves`, `invalidation_used_in_hold` (bool), `exit_order_instruction`.
  - New valuation fields: `emp_path_exit_policy_version` and `emp_path_p_invalidated_central`, which replaces `…p_stop_first…` on the V1 path.
- **Acceptance.**
  - `test_touching_a_stop_inside_one_expected_move_does_not_end_the_trade`.
  - `test_invalidation_beyond_the_noise_band_on_a_close_ends_the_trade`.
  - `test_valuation_paths_exit_by_the_same_rule_as_the_ticket`.
  - `test_missing_target_exits_at_the_planned_hold`.
- **Measurement.** Re-run `exit_rule_study.py` with the policy as shipped. Pre-registered: a paired mean at least as good as `no_stop`, and the stop share of exits below 5%. Forward: exit-reason mix and mean return by exit reason.
- **Insertion.** `signals.plan_exit` (scorer, stage 51) and `_simulate_path_exits` (stage 38).

### A5. The V1 path survives advisory-stage failure

- **Root cause (for approval).** `run_garch_layer`, `merge_garch_into_enriched` and `run_empirical_option_ev_shadow_stage` run only inside `else:` after `_eil_ok` (orchestrator L5911–5923 [C]). An advisory EIL failure therefore removes the forecast and the values that tickets need, and `prepare` then rejects every row with `FORECAST_UNAVAILABLE` or `VALUATION_MISSING`. The WS2 trigger spine raises `RuntimeError` and fails the whole evening run (L5907–5909).
- **Specification.**
  - Stages 37, 38 and 37b run whether or not EIL succeeds. The merge into EIL files stays conditional.
  - The WS2 trigger failure downgrades the legacy Lab book but does not stop stages 37/37b/38/51.
  - Run health records `v1_path_state ∈ {COMPLETE, DEGRADED(<stage>), FAILED(<stage>)}`.
- **Configuration.** None (control flow).
- **Acceptance.**
  - `test_valuation_runs_when_the_execution_intelligence_layer_fails`.
  - `test_trigger_spine_failure_does_not_stop_the_opportunity_path`: orchestrator tests with stubbed stages, run one file per process.
- **Measurement.** Forward: the share of sessions that publish a list, with a target of 100% of completed evening runs.
- **Insertion.** Evening, orchestrator L5897–5925.

### A6. GEX authority off

- **Root cause (owner-accepted, correction 8).** Ten defects (GEX-D1 to D10) in `Enhancements/gex/GEX_INVESTIGATION_20260914_214012.md`, with consumers that change decisions:
  - execution gate at 0.75× (L389–399);
  - the WBS weight in the EOD engine;
  - exit engine `EMERGENCY_EXIT` (L333–346);
  - the Lab target fallback to `wbs__wall_price` (`lab_control.py` L2872).
- **Specification.**
  - One governed flag, `legacy.gex.decision_authority` = false, is read by each consumer. When false: no size multiplier; no WBS contribution to status, tier or priority; no GEX emergency exit; no wall as a target.
  - GEX fields stay in the rows as display fields labelled `RESEARCH_GEX_UNVALIDATED`.
  - SPY/QQQ GEX refresh (`orchestrator/completed_session_gex.py`) continues as research. Its `date` parameter defect (GEX-D9) is out of V1.
- **Acceptance.** `test_actions_and_targets_unchanged_when_gex_fields_change`: a metamorphic test that perturbs the flip, walls and gamma fields and expects identical actions, sizes, targets and exits.
- **Measurement.** Forward: no row whose size or target depends on a GEX field (real-run check).
- **Insertion.** Evening stages 32, 42 and 46; morning M5.

### A7. Corporate-action contamination as a fact exclusion

- **Root cause (for approval).** DQ-12 catches one-bar moves ≥ 10× and sub-cent prices (`config/governed_constants_v1.json` `price_history_integrity`). An ordinary split (for example 2:1) is a −50% bar and passes. Corporate actions in the price store are unrepaired (blocker 8). A contaminated series corrupts the forecast, the composite and the base rates.
- **Specification.** A ticker is `CORPORATE_ACTION_CONTAMINATED` when a split or reverse split, or a special dividend of at least `opportunity.integrity.special_dividend_fraction`, falls inside `opportunity.integrity.corporate_action_lookback_sessions` (default 260, as DQ-12). The source is ranked [A]: a provider corporate-action feed first (Q7); otherwise a ratio detector that flags one-bar close ratios within ±2% of {2, 3, 4, 5, 10, 1/2, 1/3, …} without a matching open gap in adjusted history. Excluded tickers are recorded with the reason, never silently dropped.
- **Acceptance.** `test_a_split_inside_the_lookback_excludes_the_ticker_with_a_reason`; `test_missing_corporate_action_data_is_flagged_not_assumed_clean`.
- **Measurement.** Count of flagged tickers per run. Harness: IC of the composite with and without flagged names (it must not rise because of contaminated names).
- **Insertion.** Stage 37 (alongside DQ-12) and stage 37b.

### B1. Every candidate recorded and scored (the denominator)

- **Specification.**
  - New append-only table `signal_candidates` in `data/canonical/outcome_scoring.sqlite`, with one row per book row and per cross-section candidate per issue session. Fields:
    - `candidate_id`, `ticket_id` (null unless issued), `signal_version`, `run_id`, `issue_session`, `ticker`;
    - `direction`, `direction_source ∈ {LEGACY_THESIS, CROSS_SECTIONAL}`, `sleeve ∈ {OPTION, SHARES}`, `expression`, `contract_symbol`;
    - `state ∈ {ISSUED, RANKED_BELOW_CAP, FACT_EXCLUDED, NOT_VALUED}`, `reason`, `rank`;
    - `r_cautious`, `r_central` and `r_upside` for each fill model; `iv_to_forecast_ratio`; `mu_h_bps`;
    - `planned_hold_sessions`, `last_usable_session`, `stop_spot`, `target_spot`, `reference_spot`, quote fields;
    - `config_snapshot_id`, `recorded_at_utc`.
  - The table is written before the outcome is known (spec §15).
  - `score_signals` scores every candidate in state `ISSUED` or `RANKED_BELOW_CAP` with the same `plan_exit`/`mark_signal` into a new table, `candidate_outcomes`.
  - The report adds "issued vs ranked below the cap vs fact-excluded (underlying only)", with means, hit rates, the share ≥ +100%, and intervals clustered by session.
- **Configuration.** `outcome.signal.version` moves to a new version (for example SIG-V2) so the old and new records never mix.
- **Acceptance.**
  - `test_every_book_row_leaves_exactly_one_candidate_record_with_a_state`.
  - `test_candidates_below_the_cap_are_scored_by_the_ticket_exit_rule`.
  - `test_candidate_record_is_written_before_any_outcome`.
- **Measurement.** Reconciliation per run: book rows = sum of states. Forward: rank-decile monotonicity of realised return across all ranked candidates (method note 05, G4 check 1), reported and not gated.
- **Insertion.** Morning M6 (record); evening stage 51 (score).

### B2. Three fill models in valuation and scoring

- **Root cause (owner-accepted, correction 9).** The backtests assumed ask entry and bid exit. At a timed 30% of the quoted spread (Muravyev-Pearson), the top quintile moves from −26.7% to −16.7% (`fill_model_study_summary.json` [M]).
- **Specification.**

  | Fill model | Entry | Exit | e (effective spread fraction) |
  |---|---|---|---|
  | quoted | ask | bid | 1.0 |
  | timed | mid + e·½spread | mid − e·½spread | 0.30, the prior |
  | mid | mid | mid | 0; upper bound, not achievable in full |

  - Valuation publishes `emp_path_r_{cautious,central,upside}_{quoted,timed,mid}`. The exit spread uses `max(valuation.exit_spread_absolute_floor, proportional)` per spec §12.
  - Commission is `opportunity.cost.option_commission_per_contract` per side.
  - The scorer publishes `return_on_capital_{quoted,timed,mid}` and `exit_spread_fraction`.
  - The fix 1 rank key stays the quoted cautious value until C4 is adopted.
- **Configuration.**
  - New: `opportunity.cost.option_effective_spread_fraction` (0.30, PROVISIONAL, evidence Muravyev-Pearson 2020 plus the fill-model study); `opportunity.cost.option_commission_per_contract` (Q8); `valuation.exit_spread_absolute_floor` (spec Appendix B name, new).
  - Existing: `outcome.contract_multiplier`.
- **Acceptance.**
  - `test_scorer_reports_quoted_timed_and_mid_returns_for_every_closed_record`.
  - `test_timed_fill_lies_between_quoted_and_mid`.
  - `test_exit_spread_never_below_absolute_floor`.
- **Measurement.** Harness: reproduce `fill_model_study_summary.json` within rounding through the shipped code. Forward: once limit fills are journalled, the realised effective fraction is compared with 0.30. That is the only route to changing the prior.
- **Insertion.** Stages 38 and 51; morning M6.

### B3. Chains captured until every open record exits

- **Root cause (for approval).** An exit is marked only from the stored chain on the exit session. A ticker absent from the next evening's chain requests leaves the exit `MARK_UNAVAILABLE` (325 in the backtest [M]), which biases the denominator towards names that stay in the book.
- **Specification.**
  - Stage 51b writes `capture_list_{session}.csv`: every ticker with an unmatured ticket or ranked candidate, plus SPY and QQQ.
  - The next evening's chain capture (stage 19 worklist and C1 capture panel `market_data.capture_panel_source`) takes the union with the day's book.
  - The coverage of open records is reported.
- **Configuration.** `market_data.capture_open_records_enabled` (new, BOOLEAN).
- **Acceptance.** `test_an_open_record_ticker_is_on_the_next_capture_list_until_it_exits`.
- **Measurement.** Forward: the `MARK_UNAVAILABLE` share among exits, with a target below 2%.
- **Insertion.** Evening stages 51 → 19 on the next day. It costs about 1 credit per ticker per session (pipeline map S2); the added tickers are bounded by the open records.

### B4. Market-beta measurement in outcomes

- **Root cause (owner-accepted, correction 3).** Cross-sectional alpha is market-relative, but a long put needs an absolute decline. Expressing relative weakness with puts adds market beta. The two-week harness book was 64% CALL while SPY fell 2.0% [M], so direction outcomes are confounded with the market.
- **Specification.**
  - For each closed record, compute `beta_60` from 60 sessions of daily returns against SPY up to the evidence session.
  - Split the underlying return over the holding window into `market_component = beta_60 × r_SPY` and `residual_component = r − market_component`.
  - Report option and share returns by direction and by the sign of `r_SPY` over the hold.
  - The report states the share of the P&L explained by the market component.
- **Configuration.** `outcome.beta.window_sessions` (60), `outcome.condition.market_ticker` (SPY, exists).
- **Acceptance.** `test_underlying_return_splits_into_market_and_residual_that_sum_to_the_total`; `test_beta_uses_only_returns_up_to_the_evidence_session`.
- **Measurement.** Report only (R10). It feeds §9 C9 and the decision on whether puts on relatively weak names need a market-direction condition (not in V1).
- **Insertion.** Stage 51.

### B5. Stable daily list: morning step M6 and the empty-day record

- **Specification.**
  - `premarket_workflow` calls `issue_signals` after `finalize_morning_handoff` (M5) inside a guarded block. A failure of M6 is logged and does not change M4/M5 results.
  - The run publishes `signals/opportunity_funnel_{run}_{session}.json`. The fields in the list below are all counts:
    - `universe_n`, `eligible_n`, `thesis_rows_n`, `cross_section_candidates_n`;
    - `fact_excluded_by_reason{}`, `valued_n`, `ranked_n`, `issued_n{OPTION, SHARES}`;
    - `v1_path_state`.
  - When `issued_n = 0` it adds `EMPTY_DAY` with the binding reason.
  - The Markdown ticket page is kept.
- **Acceptance.**
  - `test_morning_run_publishes_a_list_or_an_explicit_empty_day_record`.
  - `test_funnel_counts_reconcile_to_the_book` (funnel reconciliation).
- **Measurement.** Forward: the share of sessions with `issued_n ≥ 1`, with a target of 100% while any candidate passes the facts.
- **Insertion.** Morning M6 (orchestrator after L7105).

### B6. Intelligence Lab V1 surface

Specified in §6. It is read-only and reads only published files and the scoring store (spec §18).

- **Acceptance.** `test_lab_opportunities_endpoint_returns_published_ranks_unchanged`; `test_lab_never_recomputes_rank_or_value`.

### C1. Cross-sectional composite (SHADOW)

- **Specification.** This promotes the pre-registered research definition (`Enhancements/research/drift_calibration.py`) into `avshunter/cross_section/`:
  1. **Eligibility per session.**
     - Median dollar volume over 20 sessions ≥ `opportunity.cross_section.min_median_dollar_volume_usd`.
     - Close ≥ `…min_price_usd`.
     - DQ-12 clean over `…integrity_lookback_sessions`, and not contaminated by a corporate action (A7).
     - A complete bar exists for the session.
  2. **Signals.**
     - S1 `reversal_5d = −(close/close[−5] − 1)`
     - S2 `low_52w_distance = close/min(low, 252) − 1`
     - S3 `momentum_12_1 = close[−21]/close[−252] − 1`

     Each signal is z-scored cross-sectionally and winsorised at ±`…winsor_z` (3). A ticker is scored only when all three are available; otherwise it is `NOT_SCORED(reason)`, never 0 (R1).
  3. **Composite.** The mean of the z-scores (the linear baseline; correction 4). The decile is assigned per session.
  4. **Calibration of μ_H.**
     - For each decile d, μ_H(d) is the mean market-relative forward log return at horizon H = `opportunity.planned_hold_sessions`, from an expanding walk-forward window that ends H sessions before the evidence session (no look-ahead).
     - The interval is a session-block bootstrap (`outcome.bootstrap_resamples`, `outcome.interval_quantiles`).
     - It is shrunk towards 0 by `n_eff`.
     - Recalibrated every `…recalibration_sessions`.
  5. **Output per ticker.**
     - `composite_z`, `composite_decile`;
     - `mu_h_bps`, `mu_h_low_bps`, `mu_h_high_bps`;
     - `beta_60`, `sigma_h_bps` (Layer 3 at H);
     - `calibration_version`, `authority_state = SHADOW`.
- **Evidence and limits [M].**
  - The composite's IC is about 0.017–0.021, with t ≈ 3.1 at 1 session.
  - Its gross top-minus-bottom decile spread is 30–32 bps at 5 sessions and 41–54 bps at 10.
  - **The pre-registered pass was not met at the primary 5-session horizon**, where t was 1.26–1.68 (`drift_calibration_summary*.json`).
  - Net figures in those files use the Abdi-Ranaldo cost (57–72 bps), which the owner does not accept as credible for liquid names (realistic 2–10 bps [A]).

  μ_H is therefore a SHADOW input.
- **Configuration.** `opportunity.cross_section.{signals, winsor_z, min_price_usd, min_median_dollar_volume_usd, integrity_lookback_sessions, deciles, calibration_start, recalibration_sessions, shrinkage_rule}`.
- **Inputs.** `data/canonical/historical_prices.sqlite` via `adapters/prices.load_price_panel`, and Layer 3 output.
- **Outputs.** `R/cross_section/cross_section_scores_{run}.csv`, plus the calibration table `R/cross_section/decile_calibration_{version}.csv`.
- **Acceptance.**
  - `test_composite_uses_only_bars_up_to_the_evidence_session`.
  - `test_missing_signal_means_not_scored_not_zero`.
  - `test_research_script_and_production_module_give_identical_ic_on_a_frozen_panel` (one implementation).
- **Measurement.** Nightly IC and decile spread appended to a forward log. A walk-forward report by year, with the pre-registered criteria unchanged.
- **Insertion.** Evening stage 37b (after 37, before 38).

### C2. Share cost model (share tickets stay disabled until it passes)

- **Root cause (owner-accepted, correction 10).** The Abdi-Ranaldo estimator is floored at zero (0 on 14.4% of valued rows in run 20260917_214854 [M]) and overstates cost for liquid names (57–72 bps round trip in the drift study [M] against the owner's 2–10 bps [A]).
- **Specification.**
  1. **Capture.** At every morning issue (M6), record the live NBBO bid, ask and size for every share candidate from the same provider snapshot the morning gate uses (`morning_gate._fetch_live_price`, L797). Entitlement to quote fields is [A] and part of Q6. Record it in `share_quote_observations`.
  2. **Cost table.** Median quoted half-spread by bucket (price tercile × 20-session median dollar-volume decile), rebuilt nightly from at least `opportunity.cost.share_quote_min_sessions` (20) sessions.
  3. **Effective round-trip cost.**

     ```text
     cost_bps = 2 × e_share × half_spread_bucket + commission_bps
     ```

     `e_share` = `opportunity.cost.share_effective_spread_fraction`, with a provisional prior of 0.5 [A], to be measured from journal fills. Market impact is zero because size is out of scope; this is disclosed.
  4. **Missing data.** A live quote at issue replaces the bucket when present. No bucket with enough data means `SHARE_COST_UNAVAILABLE`, never 0.
- **Configuration.** `opportunity.cost.{share_effective_spread_fraction, share_quote_min_sessions, share_commission_per_share, share_bucket_scheme}`; `opportunity.shares.enabled` = false until acceptance.
- **Acceptance.**
  - `test_share_cost_is_measured_or_unavailable_never_zero`.
  - `test_live_quote_overrides_bucket_estimate`.
- **Measurement.** After 20 sessions: the bucket medians with intervals, and the out-of-sample error of the bucket estimate against the next day's live quote. Pre-registered pass: median absolute error ≤ 2 bps for the top two dollar-volume deciles [A].
- **Insertion.** Morning M6 (capture); evening stage 51 (table build).

### C3. One path valuation for both expressions, with drift as a switch

- **Root cause (for approval).** Shares are valued only when an option contract exists (977 of 1,498 rows unvalued [M]). This breaks spec S2 ("no chain → shares still valued"). Share return is measured per unit of risk to the stop, which A4 removes. Valuation has zero drift (`empirical_option_ev.py:368`), so share values are cost-only and the expression choice has no content (drift study docstring).
- **Specification.**
  - **Shares valued independently.** `_simulate_path_exits` runs for every ticker with a forecast and a geometry. An option contract is not required. The share value does not depend on the option.
  - **Share return per notional.**

    ```text
    r_share = sign · (exit_net − entry) / entry
    entry   = spot·(1 + sign·cost/2)
    ```

    Here cost is the C2 figure.
  - **Share scenarios.**
    - cautious = the lowest of the three volatility scenarios with μ_H at `mu_h_low_bps`;
    - central = the p50 scenario with μ_H;
    - upside = the highest scenario with `mu_h_high_bps`.
  - **Drift.** When `opportunity.drift.injection_enabled` is true, paths carry daily drift μ_H/H in log terms, added to the calibrated innovations for both expressions on the same path set (spec §12 common-path rule). When false, values equal today's (characterisation). μ_H is market-relative; the option leg records `mu_h_bps` and `beta_60` side by side, with no market forecast (§9 C9).
- **Configuration.** `opportunity.drift.injection_enabled` (false until C1 is reviewed); `opportunity.drift.source_version`.
- **Outputs.**
  - `emp_share_r_{cautious,central,upside}_{fill}` (per notional);
  - `emp_share_quality_flag`;
  - `emp_drift_bps_applied`;
  - `emp_drift_state ∈ {OFF, APPLIED, NOT_SCORED}`.
- **Acceptance.**
  - `test_zero_drift_reproduces_current_option_values` (characterisation).
  - `test_shares_are_valued_without_an_option_contract`.
  - `test_share_return_is_per_notional_and_net_of_measured_cost`.
  - `test_same_paths_value_option_and_share`.
- **Measurement.** Harness with the switch off and on. Pre-registered: rank IC of the option cautious value against realised return is not lower with drift on (baseline 0.44).
- **Insertion.** Stage 38.

### C4. Expression by expected move against effective cost, and the opportunity score

- **Specification (combine, don't stack; owner correction 1).**
  - **Option hurdle.** `h_opt_bps` is the drift at which the option's central value under the timed fill equals zero, found by bisection on the C3 path set. It is lower when implied volatility is cheap relative to the forecast. This is where the option alpha (Goyal-Saretto, in single-leg form) enters, and it enters once, through value. The hurdle for an at-the-money contract is expected near 200 bps [A, owner figure]. It is published with `iv_to_forecast_ratio = contract_iv / l3_forward_realised_vol_raw`.
  - **Share hurdle.** `h_sh_bps` = C2 cost_bps.
  - **Edges, in underlying bps over H.**

    ```text
    edge_opt = sign·μ_H − h_opt
    edge_sh  = μ_H − h_sh       (long only in V1; BEAR → SHORT_SHARES_OUT_OF_SCOPE)
    ```

  - **Expression.** The argmax of the edges over the available expressions (shares enabled, option executable). If every edge is ≤ 0, the argmax is still recorded, as `NO_POSITIVE_EDGE` (visible, ranked below; spec §13).
  - **Opportunity score.** `score = edge_chosen / sigma_h_bps` (edge in expected moves, comparable across tickers and expressions). It is not added to any other score, so the two alphas are combined and not stacked.
  - **Adoption rule (pre-registered).** The score replaces the fix 1 key (quoted cautious value) for the option sleeve only if its walk-forward rank IC against realised timed return is at least the cautious-value IC minus 0.02 on the harness, and higher on at least 15 forward issue sessions. Until then it is published beside the rank.
- **Configuration.** `opportunity.expression.choice_rule_version`, `opportunity.expression.hurdle_fill_model` (`timed`), `opportunity.ranking.key` ∈ {`CAUTIOUS_QUOTED`, `OPPORTUNITY_SCORE`}.
- **Outputs.** `h_opt_bps`, `h_sh_bps`, `edge_opt_bps`, `edge_sh_bps`, `expression_choice`, `expression_choice_reason`, `opportunity_score`, `iv_to_forecast_ratio`.
- **Acceptance.**
  - `test_the_expression_is_the_one_whose_expected_move_clears_its_cost_by_more`.
  - `test_cheaper_implied_volatility_lowers_the_option_hurdle`.
  - `test_no_positive_edge_is_recorded_not_dropped`.
  - `test_ranking_key_follows_configuration`.
- **Measurement.** Harness plus forward, as in the adoption rule. The money-location check (method note 05, G4 check 3): do the option-or-share choices agree with the realised relative returns more often than chance?
- **Insertion.** Stage 38 (values) and morning M6 (rank).

### C5. Share sleeve issuance

- **Specification.**
  - When `opportunity.shares.enabled` is true, M6 ranks every long-share candidate by `opportunity_score`. No threshold on the score excludes a candidate: a non-positive edge is ranked and labelled `NO_POSITIVE_EDGE`. M6 then issues the top `opportunity.shares.max_tickets_per_session`.
  - The ticket carries: limit = live price moved by e_share × half-spread, the C2 cost, `mu_h` with its interval, the planned hold, exit by A4 (no stop inside the hold, invalidation rule where a structural level exists, otherwise hold only), and the cautious, central and upside values per notional.
  - Every share candidate is recorded in B1.
- **Precondition.** C2 accepted and C3 shipped.
- **Acceptance.** `test_share_tickets_stay_disabled_until_the_cost_model_is_accepted`; `test_share_ticket_carries_cost_drift_interval_and_hold`.
- **Measurement.**
  - Forward: realised net return per share ticket and per not-issued share candidate by decile.
  - The pre-registered forward check is that the decile spread net of the measured cost is above zero with a session-clustered interval. It is a report, not an authority.
- **Insertion.** Morning M6.

### R1–R6. Research items (not on the V1 critical path; results decide what enters C4)

| # | Study | Specification | Data | Output |
|---|---|---|---|---|
| R1 | Goyal-Saretto in long single-leg form (correction 2) | Quintiles of `iv_to_forecast_ratio` at entry. Realised return on premium per quintile under three fill models, for calls and puts separately, clustered by session, with no delta hedging. Observation to test: winners were bought at 0.69× the forecast, losers at 0.86× (research programme §2). | Harness rows (contract IV, Layer 3 raw forecast) | Does cheap implied volatility pay a long single-leg holder? It enters only through C4's hurdle, never as a separate score |
| R2 | Options-market direction signals in single-leg form | O2 call-put IV spread (Cremers-Weinbaum); put-call volume ratio (Pan-Poteshman); option-to-stock volume O/S (Johnson-So). Deciles, then long calls on the favoured side and long puts on the unfavoured side, with market beta reported (B4) | `iv_surface_history` (`put_call_iv_spread`, `total_volume`; weekly since 2026-05-22), `chain_snapshots.volume`, price store | A candidate direction source for options. Enters only after a pre-registered pass and an owner decision |
| R3 | Earnings convexity (Chung-Louis) | Buy near-ATM before the announcement and exit at the announcement | Needs a point-in-time earnings calendar (Q3) | Deferred until the data exists; event flag is display-only meanwhile |
| R4 | Planned-hold study (feeds A2) | Harness at H ∈ {5, 10, 15, 20} under the A3 and A4 rules. Metrics: paired mean, expiry-cap share, hit rate, share ≥ +100%. The multiple-testing count is recorded (four variants) | Harness | The value of `opportunity.planned_hold_sessions` |
| R5 | Matched contract by value (spec §10 alignment) | Value the bounded set from A3 and choose the highest cautious (timed) value. Compare with the A3 deterministic rule on paired theses | Harness and chain store | Adopt if the paired mean and median are not worse |
| R6 | Challenger protocol (correction 4) | GBM or NN models only as registered challengers to the C1 linear composite. Walk-forward, purged and embargoed (method note 06 §3). Pre-set hurdle: rank IC improvement ≥ `opportunity.challenger.min_ic_improvement` with a deflated t ≥ 3 [A] | — | Not in V1 |

---

## 5. Ordered build plan

Each row is one approved change: characterise → failing business-rule test → minimal change → acceptance on the harness and forward sessions. The approval column gives what ACK has to approve before the code change.

| Order | Item | Depends on | Approval needed | Why this position |
|---|---|---|---|---|
| 0 | A0: rank, don't gate (fix 1) | — | Given (ACK-20260918-RANK-NOT-GATE); **in progress** | Ends zero-ticket days |
| 1 | A5: V1 path independent of EIL and trigger failure | — | **Root cause and design** (new finding) | Without it a failed advisory stage empties the list |
| 2 | A1: ticket path reads facts, not `final_action` | A0 | **Root cause and design** (new finding: 904 of 1,498 rows vetoed by legacy labels) | Largest remaining source of empty days |
| 3 | R4: horizon study | — | None (research in `Enhancements/`); pre-register first | Sets the A2 value |
| 4 | A2: canonical planned hold (config and readers) | R4 | Design; **value of H** | Root cause accepted (correction 6) |
| 5 | A3: fact-only selector, deterministic match | A2 | **Root cause** (forecast vetoes in the selector) and design | Contracts outlive the plan; more rows get a contract |
| 6 | A4: exit policy without a stop inside the hold | A2 | Design; **definition of thesis invalidation** (§9 C3) | Root cause accepted (correction 7) |
| 7 | A6: GEX authority off | — | Design (root cause accepted, correction 8) | Independent; can run in parallel with 4–6 |
| 8 | B1: candidate ledger and scoring | A0 | Design | The denominator; needed to measure everything after it |
| 9 | B2: three fill models | B1 | Design (correction 9; see §9 C4) | Correct economics in every later measurement |
| 10 | B3: capture until exit | B1 | **Root cause and design** | Removes the survivorship in exit marks |
| 11 | B5: morning step M6 and funnel | A1, B1 | Design | The daily list becomes automatic |
| 12 | B4: beta split | B1 | Design | Measures correction 3 |
| 13 | B6: Lab surface | B1, B5 | Design | The product surface |
| 14 | A7: corporate-action exclusion | — | **Root cause, design and data source** (Q7) | Before C1 goes live |
| 15 | C1: cross-sectional composite (shadow) | A2, A7 | Design | Supplies μ_H |
| 16 | C2: share cost capture and model | B5 | Design; data entitlement (Q6) | 20 sessions of capture needed before C5 |
| 17 | C3: shares valued without a contract; drift switch | C1, C2 (for share values), A4 | **Root cause** (share valuation coupled to the contract) and design | One path valuation |
| 18 | R1: IV/forecast single-leg re-test | B2 | None (research) | Decides whether the option hurdle story holds |
| 19 | C4: expression rule and opportunity score | C3, R1 | Design; **adoption vote** on the pre-registered result | Expression by edge size |
| 20 | C5: share sleeve issuance | C2 accepted, C3, B1 | Design; **owner go-live** | Shares in the daily list |
| — | R2, R3, R5, R6 | as stated | Research pre-registration | Not on the critical path |

A6, A7 and R4 have no dependency on A1–A5 and can be approved and built in parallel. Every item that changes pipeline code follows CLAUDE.md: no code change without an approved root cause and design.

---

## 6. What the Intelligence Lab must display for V1

The Lab is a read model (spec §18). It adds one tab, **Opportunities**, backed by read-only endpoints:

- `/api/opportunities/<run_id>`, which reads `signals/signal_tickets_*.csv`, `signals/opportunity_funnel_*.json` and the `signal_candidates` rows;
- `/api/opportunity_track_record`, which reads `outcome_scoring.sqlite` (`signal_tickets`, `signal_candidates`, `signal_outcomes`, `candidate_outcomes`) opened read-only.

It never recomputes a rank, value or priority (`test_lab_never_recomputes_rank_or_value`).

| Panel | Content |
|---|---|
| Header | Session, run_id, `v1_path_state`, configuration snapshot id, quote feed state (`DELAYED_PROVIDER_FEED`, 900 s), and the label *"Decision support · SHADOW · no capital authority · G1–G4 not passed"* |
| **Funnel (the denominator)** | Universe → eligible → thesis rows / cross-section candidates → fact exclusions by reason (each code with its count) → valued → ranked → issued (options, shares). `EMPTY_DAY` shown with its binding reason |
| **Today's list** | Rank; ticker; direction; `direction_source`; expression and `expression_choice_reason`; contract (OCC, strike, expiry, DTE, DTE cover, moneyness); limit price and order instruction; spot at issue; invalidation and whether it is used in the hold; target or `NONE`; planned hold and last usable session; cautious / central / upside under quoted and timed fills; `iv_to_forecast_ratio`; `mu_h_bps` with its interval (SHADOW); hurdles and edges (after C4); quote state and delta-adjustment state; DQ-12 and corporate-action state |
| **Ranked below the cap** | The same columns for every ranked candidate not issued, so the owner sees what the cap left out |
| **Track record** | Issued vs ranked-below-cap vs all, by sleeve and fill model: count closed, issue sessions, hit rate, mean and median, clustered interval, share ≥ +100%, worst, maximum drawdown (equal weight), exit-reason mix, predicted central value against realised, and the market / residual split (B4). The `signals.evaluate` verdict is shown as a report |
| **Rank quality** | Realised return by rank decile across all ranked candidates, with the Spearman IC and interval. This is the one chart that shows whether the ranking works |
| Display-only context (labelled) | Macro context (routine file), event flag (earnings date if known, "unverified source"), GEX (`RESEARCH_GEX_UNVALIDATED`), O4 stance, H9R flag. None of them sorts or filters the list |
| Data health | Chain capture coverage, open-record capture coverage (B3), price-store freshness, universe size against the target (3,320 / 6,500), share-cost sessions captured (C2) |

The legacy Lab book, its tabs and the legacy EV labels stay as they are. The Opportunities tab never shows legacy EV v2 or EV3 as a value (CLAUDE.md rule 5).

---

## 7. Open questions for the owner

| # | Question | Why it matters | Evidence |
|---|---|---|---|
| Q1 | **Long-dated chains.** Buy or capture chains to 3–12 months (raise `market_data.chain.to_offset` from 60, with the credit budget)? | Convex, event and far-OTM strategies cannot be tested at all today | Stored chains only cover 8–45 DTE (blocker 6); capture `to_offset` = 60 |
| Q2 | **Trade-level flow.** Buy OPRA-level trades (sweeps, blocks)? | The main signal competing products use; R2 can only use end-of-day volume | Blocker 7 |
| Q3 | **Point-in-time event calendar.** Buy one, or build it from recorded announcements? And does the "event" part of correction 1 override the display-only rule (§9 C6)? | R3 and any event sleeve need it | Earnings source is unreliable (method note 04 pitfalls) |
| Q4 | **Short selling of shares.** Allow short shares (with borrow availability and fee data) for bottom-decile names? | Without it, relative weakness can only be expressed with puts, which carry market beta (correction 3) | Spec §10 includes short shares subject to borrow |
| Q5 | **Universe restoration from 3,320 to 6,500.** Run the MarketData scanner and restore the full universe? Cost and schedule? | Doubles the cross-section breadth (C1 benefits most) | Scanner manifest from 20 Aug is ignored as stale; universe file dated 17 May (pipeline map S1) |
| Q6 | **Real-time option quotes and share NBBO.** Upgrade from the 15-minute delayed entitlement? Confirm the share quote fields are available for C2 | Delayed quotes need delta adjustment; C2 needs live share quotes | `config/governed_constants_v1.json` `option_quote_feed` |
| Q7 | **Corporate-action source.** Provider feed or ratio detector for A7? | Integrity fact | Blocker 8 |
| Q8 | **Broker commissions and fills.** Per-contract and per-share commissions, and consent to journal limit fills against `ticket_id` so the effective-spread prior can be measured | B2 and C2 priors | Muravyev-Pearson prior is unvalidated on our fills |
| Q9 | **Daily caps.** Keep N = 5 for options, and set N for shares? Should the cross-sleeve order be shown as one list or as two sleeves? | Product surface | `outcome.signal.max_tickets_per_session` = 5 |
| Q10 | **Planned hold.** Approve the R4 protocol and the provisional 10 sessions | A2 | §4 A2 |

---

## 8. Map to the eleven blockers (`MONETISATION_BLOCKERS_20260918.md`)

| # | Blocker | V1 status | Items / reason |
|---|---|---|---|
| 1 | Direction: no demonstrated edge | **Partly addressed; not solved** | C1 makes the one robust tilt (composite) an explicit, measured, SHADOW input to shares, where its size (about 0.1–0.5%) is relevant. The option direction stays `LEGACY_THESIS`, and the composite's disagreement only lowers value (C3/C4). R2 tests options-market direction signals in single-leg form. No V1 item claims direction skill |
| 2 | Issuing rule rejects the winners | **Addressed** | A0 (in progress) plus A1 (removes the legacy-label veto) |
| 3 | Exit geometry | **Addressed** | A4 (+2.9 points, t = 3.21); valuation uses the same rule |
| 4 | Contracts expire before the plan | **Addressed at source** | A2 (one hold), A3 (selector DTE from the hold); the ticket guard remains |
| 5 | Execution cost | **Addressed** | A3 (one spread limit, 10%), B2 (three fill models, timed prior), A4 (limit orders; no market sells into wide quotes), C2 (share cost) |
| 6 | Tail not in the instruments | **Deferred** | Needs long-dated chains (Q1). V1 deliberately stays near the money (moneyness limit; Boyer-Vorkink; OTM study −62% to −78%) |
| 7 | Missing data | **Mostly deferred** | Q1–Q3, Q5, Q6. V1 adds open-record capture (B3) and share quote capture (C2) from existing entitlements |
| 8 | Data integrity | **Partly addressed** | DQ-12 kept; A7 adds corporate actions; A6 removes GEX authority. The US Money Index and macro are out of V1 (display-only by decision) |
| 9 | Gate architecture produces empty days | **Addressed for the V1 path** | A0, A1, A3 (forecast vetoes removed), A5 (failure isolation), B5 (explicit `EMPTY_DAY`). The legacy ladders stay for the legacy Lab only |
| 10 | Nothing validated forward | **Addressed as measurement; authority deferred** | B1 (every candidate scored), B2, B4, B6 track record. The trust gate stays a report; capital authority is out of scope |
| 11 | Product framing | **Addressed** | The V1 definition itself: a daily ranked list published with its full denominator (§1, §6) |

---

## 9. Conflicts between the owner corrections and the governing documents (for ACK; not resolved here)

| # | Conflict | Governing text | Correction or V1 design |
|---|---|---|---|
| C1 | Pre-valuation contract selection | Spec §2 ("no contract selector stage"), §10 ("no weighted score … delta bands … to pre-select contracts"), §26; method note 05 §1 | V1 publishes one matched contract per candidate (A3). R5 moves towards "value the bounded set, pick by value" |
| C2 | A single planned hold, and a contract that must outlive it as a hard exclusion | Spec §9 (no single `hold_sessions`, no holding bucket), §10 and A.2 decision C3 (shorter-dated expressions valid with their own `last_exit_session`; "minimum-DTE exclusion removed"), §21, §26; note 05 lists "DTE required to cover a fixed hold bucket" as a pitfall | Corrections 5 and 6; A2 and A3 |
| C3 | Removing the underlying stop while keeping "thesis invalidation" | Spec §8, §9, §12, §16: invalidation is the structural stop, and paths resolve `STOP_FIRST` at its touch | Correction 7. A4 defines invalidation as a close beyond a level at least 1.5 expected moves away, which needs ACK confirmation |
| C4 | Costs better than quoted | Spec §12 (entry at ask, exit at bid); note 03 §3 ("a rule must be validated on our fills before using anything better than quoted"); note 06 §3.5 | Correction 9: 30% effective spread as the prior. B2 keeps quoted as the fix 1 rank key and reports all three |
| C5 | Implied versus forecast volatility in the score | Spec §11, §13 and Invariant G; note 04 §6 (cheap convexity is not a ranking key until validated, to avoid double counting) | Correction 1 puts option alpha in the opportunity score. C4 enters it once, through value (the hurdle), not as an added score |
| C6 | Events influencing options | CLAUDE.md rule 6 and spec §14 and §26 (event information is display-only, never a gate, score or rank) | Correction 1 ("events drive options") and correction 7 ("event complete" exit). V1 keeps events display-only pending ACK |
| C7 | Ranking and issuing on unvalidated measures | Spec Invariant G, §24; Appendix B (a value not `VALIDATED` may drive shadow behaviour only); pipeline map S13.5 ("RAEV ≤ 0 cannot become BUY") | Fix 1 issues the top N by cautious value even when every value is negative. All V1 configuration is PROVISIONAL. V1 can be consistent only if the published list is formally a shadow, decision-support product |
| C8 | Ranking key | Spec §12 and §13: RAEV (lower-bound EV per $ at risk including evidence uncertainty) with a time-normalised tie-break | Fix 1 ranks by the cautious value (the lowest of three volatility scenarios; no evidence uncertainty) |
| C9 | A second direction producer, and symmetry | Spec Invariant A and §25 (direction owned by Thesis); R2 "one owner per fact"; Invariant D (BULL and BEAR treated symmetrically) | Correction 1 makes the cross-sectional composite the direction and expected-move source for shares. Long-only shares in V1 give BEAR candidates no share expression |
| C10 | Expression scope | Spec §10 approved scope includes debit verticals and short shares (scope changes are "business decisions, versioned in configuration") | V1 excludes both. A configuration version recording the scope decision is needed |
| C11 | Quote age as an exclusion | Spec §10 tradeability lists "stale quote"; `EXECUTABLE_QUOTE` includes a freshness check (`long_option_execution.py`) | Owner guidance (memory "fresh or flagged"; `signals.py` treats quote age as a flag) and correction 5 ("two-sided executable quote") |
| C12 | The composite did not pass its own pre-registration | `drift_calibration.py` pass rule: \|t\| ≥ 3 on non-overlapping samples and a net spread > 0 at 5 sessions. Measured t at 5 sessions was 1.26–1.68 | Correction 1 builds the share sleeve on it. The owner rejects the cost half of the test (Abdi-Ranaldo), but the t criterion also fails at the primary horizon |
| C13 | Strangler versus enhance in place | Pipeline map v2.0 §5 and §7 and the knowledge README still prescribe strangler migration and retire `empirical_option_ev.py`, the selector and the horizon router | CLAUDE.md rule 4 (ACK D1, 17 Sep 2026) replaces this. The lower documents are not yet marked superseded (document hygiene, no design conflict) |

Two factual notes found while writing:

- The "71% median exit spread on stop exits" (correction 7) is not in any repository file I could find. The fill-model study reports 60.9% across all exits.
- The execution-gate GEX penalty is at `execution_gate.py` L389–399, not L371–398 as the GEX investigation states.
