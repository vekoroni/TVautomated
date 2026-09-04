# AVSHUNTER Intelligence Lab: Functionality and Data Roadmap

**Status:** Source specification for production of the trader user guide  
**Prepared:** 25 August 2026  
**Audience:** Junior traders, supervising traders, pipeline operators, developers, testers, and the GPT producing the final guide  
**Governed schema:** `lab_signal_book_v2`  
**Governed browser source:** `GOVERNED_FINAL_OPPORTUNITY_BOOK_V2`  
**Current contract size:** 232 fields

## 1. Purpose

This document explains the Intelligence Lab's functionality, the data it displays, where that data enters the pipeline, and how each data family should be used during trade preparation, morning validation, execution, management, and review.

It is both a current-state specification and a development roadmap. A guide generated from it must clearly label:

- **Current production:** implemented and governed now.
- **Current limitation:** available only with manual or supervisory control.
- **Roadmap:** proposed functionality that must not be described as live.

The Intelligence Lab is intended to be the trader's single working interface. A user should not search raw CSV or JSON files to construct a trade. The Lab presents the committed pipeline result; it does not promise a profitable outcome.

## 2. Operating principles

1. **One governed signal source.** The Lab reads the final opportunity book. It does not independently create, promote, or repair signals.
2. **Lineage before execution.** A displayed idea must be tied to a run, source row/payload, completed controls, and current morning decision.
3. **Morning validation before live entry.** An evening result is a prepared thesis. `requires_live_validation` and the morning fields determine whether it needs trading-day validation.
4. **Macro is advisory.** Macro, bond, auction, and sector-rotation data add context; they do not impose a universal GO/NO-GO decision or force CALL/PUT direction.
5. **EV is advisory.** EV3 assesses option economics and uncertainty. `ev3_shadow_only` confirms its current non-authoritative role; it does not independently grant or remove trade permission.
6. **Missing is not neutral.** Missing, stale, unavailable, not applicable, not evaluated, zero, and neutral must remain distinct.
7. **No complete numeric ticket, no unsupervised order.** A live trade requires exact contract, limit, multiplier, quantity, maximum monetary loss, trigger, invalidation, target, and exit rule.

## 3. Current source of truth

For run `{run_id}`, the governed Lab artefacts are committed under:

```text
data/output/runs/{run_id}/intelligence_lab/
    final_opportunity_book_{run_id}.json
    final_opportunity_book_{run_id}.csv
    lab_triage_view_{run_id}.csv
```

The final opportunity book is the authority. `lab_triage_view` is a display/export view of the same governed contract, excluding only `source_payload_json`; it is not a competing selection engine. Intermediate pipeline files remain useful for debugging and audit, but must not be used by a trader to bypass the final book.

The browser should identify the loaded data as:

```text
GOVERNED_FINAL_OPPORTUNITY_BOOK_V2
lab_signal_book_v2
```

## 4. End-to-end functional flow

```text
Market and reference inputs
        |
        v
Discovery, technical state and core model computation
        |
        v
Direction, intent, structure, trigger and horizon governance
        |
        v
Options contract selection, quote normalisation and economics
        |
        v
Actuarial + market physics + catalyst + GEX/WBS + GARCH + EIL evidence
        |
        v
Evening candidate preparation
        |
        v
Morning validation: changed price/trigger/contract/conflict state
        |
        v
Final opportunity book: one committed baton
        |
        v
Intelligence Lab: triage, details, execution control and audit
        |
        v
Manual broker execution under current operating model
        |
        v
Trade journal, realised outcome and model feedback
```

Macro operates as a parallel context system:

```text
Macro + bond + auction + sector rotation
        |
        +----> macro_regime / sector_tilt / regime_drift_status / macro_data_role
                   contextual value only; never sole trade permission
```

## 5. Data ownership, timing and trader use

| Data family | Produced by | Timing | Function | Correct use | Authority |
|---|---|---|---|---|---|
| Identity and rank | Lab compiler/orchestrator | On commit | Identifies run and idea; orders the work queue | Confirm current run and stable trade idea | Control |
| Lab authority | Lab control contract | Evening plus morning reconciliation | States tradeability, preparation, execution and coherence | Decide execute/wait/repair/block | Primary control |
| Morning state | Morning gate | Trading day | Revalidates changed inputs and unlock conditions | Required where live validation is flagged | Primary control |
| Direction/conflicts | Direction resolver and Lab reconciliation | Evening/morning | Sets canonical CALL/PUT expression and exposes disagreement | Use `canonical_direction`; escalate hard conflicts | Primary control |
| Contract and liquidity | Options intelligence/normaliser | Evening, checked morning | Selects contract and records quote/liquidity/repair state | Verify exact contract at broker | Primary control |
| RR and EV3 | Options economics/EV3 | Evening | Tests option economics and uncertainty | Compare structures and diagnose weak economics | Advisory |
| Actuarial/behaviour | Vanguard actuarial layer | Evening | Supplies historical comparable-state evidence | Weight by match type, confidence and sample | Advisory |
| Catalyst | Catalyst enrichment | Evening/context refresh | Describes event timing, truth and directional bias | Manage binary-event exposure and DTE | Risk context |
| Market physics | Vanguard/physics model | Evening | Describes energy, force, transition and liquidity friction | Understand mechanism and regime change | Advisory |
| Macro/sector | Standalone macro system | Independent schedule | Adds regime/sector drift context | Sector preference and risk awareness only | Advisory |
| EIL | Evidence integration layer | Evening | Summarises signal evidence | Explanation, not a second execution authority | Advisory |
| Price/target plan | Core structure and trade-plan layers | Evening/morning | Defines entry, invalidation, target, runway and feasibility | Bound thesis and exit conditions | Control-critical |
| Greeks/volatility | Option/GARCH calculations | Evening | Measures option sensitivity, volatility value and expected move | Select contract/tenor and understand decay | Advisory/risk |
| GEX/WBS | Governed GEX and wall-break scorer | Evening | Maps walls and ranks break potential | Structure targets, stops and timing | Advisory |
| Readiness/time stop | Stage ladder/time-stop layer | Evening/morning | Describes campaign progression and checkpoints | Manage timing; cannot override permission | Operational |
| Data quality/provenance | Lab compiler | On commit | Makes missing data and source lineage visible | Block/escalate critical defects | Control |

## 6. Daily trading lifecycle

### 6.1 Evening preparation

The evening run discovers and ranks candidates using completed market data. The trader may review direction, phase, intent, regime, contract, economics, targets, wall evidence, volatility, catalysts, and potential morning unlock conditions.

Evening labels such as an EOD candidate or trigger-ready preparation do not by themselves authorise a live order. If `requires_live_validation` is true, the morning gate must resolve the row.

### 6.2 Morning validation

The morning gate reconciles the prepared idea with the state that can change before entry. The trader checks:

- `morning_data_state` is usable and current;
- `morning_execution_permission`, `morning_execution_route`, and `morning_execution_lane` agree;
- `morning_entry_action` is consistent with `lab_tradeable` and `lab_execution_status`;
- the `morning_unlock_condition` has actually been satisfied;
- morning/Lab alignment is valid and its reason is intelligible;
- current contract selection or required repair is explicit;
- no conflict or execution lock remains.

The morning gate should validate changed data, not use macro as a universal veto and not casually rediscover a different thesis.

### 6.3 Entry

Before opening a broker ticket, the trader must confirm:

- ticker, `canonical_direction`, instrument, contract symbol, strike, expiry and DTE;
- current bid, ask, mid, quote source/time where available, spread and liquidity;
- trigger, price source, trigger evidence and trigger data state;
- invalidation price, target, target zone and time stop/checkpoint;
- planned limit, multiplier, quantity, total debit/credit and maximum monetary loss;
- Lab authority, morning permission, conflicts, vetoes and repair status.

If a required control is absent, the correct state is manual review or repair—not estimation by a junior trader.

### 6.4 Monitoring and exit

Monitor the original thesis rather than option P&L alone:

- underlying price relative to trigger, invalidation, target and GEX wall;
- time remaining relative to hold window, checkpoint and expiry;
- current option liquidity and spread;
- volatility/decay relative to the entry thesis;
- event timing and any new hard veto;
- wall-stall, phase, and stage-readiness guidance.

Record actual order, fill, fees, partial exits, final exit, reason and realised P&L. The learning objective is profitable, risk-controlled closes—not merely a high count of generated candidates.

## 7. Permission hierarchy

The user guide must derive action from the complete authority family, not from one colourful badge.

| Effective condition | Meaning | Junior action |
|---|---|---|
| `lab_tradeable = true`, executable `lab_execution_status`, valid morning permission, no lock/conflict | Governed permission | Verify numeric ticket and submit exact approved order |
| Limit/probe lane | Restricted permission | Use only governed limit/size; do not chase or enlarge |
| Prepared/armed/waiting | Valid thesis, entry condition not met | Monitor; no order |
| `requires_live_validation = true` without valid morning state | Evening preparation only | Run/await morning validation; no order |
| `contract_repair_required = true` | Contract is not currently fit | No order until governed repair completes |
| Hard conflict, hard veto or `execution_lock_reason` | Prohibited | No order; escalate if diagnosis is needed |
| Coherence/data-state failure | Contract contradicts itself or required data is defective | No order until corrected and recommitted |

The safest state controls whenever badges disagree.

## 8. Numeric execution ticket

### 8.1 Required figures

A ticker, direction and score are not a controlled trade. A production execution ticket must contain:

- exact strategy and all contract legs;
- contract multiplier and adjusted-contract flag;
- current quote time, bid, ask and proposed limit;
- approved quantity;
- planned debit/credit in account currency;
- maximum monetary loss and maximum profit where defined;
- account risk percentage and risk-budget source;
- trigger, invalidation, target and time stop.

### 8.2 Arithmetic

For a standard long option:

```text
planned debit = premium per share x multiplier x contracts
maximum loss = planned debit + fees
```

For a vertical debit spread:

```text
net debit per share = long premium - short premium
maximum loss = net debit per share x multiplier x spreads + fees
gross spread value = strike width x multiplier x spreads
maximum gross profit = gross spread value - maximum loss
```

Never assume a multiplier of 100 for an adjusted/non-standard contract.

### 8.3 Current limitation

The current 232-field contract governs contract identity, mid/bid/ask, spread, liquidity, entry/invalidations/targets, and model evidence. It does **not** yet govern the full monetary order ticket: multiplier, approved quantity, planned limit, total debit, maximum loss, maximum profit, and account-risk percentage are not canonical fields.

Therefore the current Lab is a governed signal-review cockpit, but junior sizing and maximum monetary risk remain supervised. The generated user guide must not claim autonomous execution.

## 9. Intelligence Lab screen guide

### Triage table

Use the table as a work queue. Confirm the current run, exclude locked/defective rows, filter for the intended permission lane, then open the complete record. Rank, conviction, positive RR, positive EV or a green badge never replaces the full control check.

### Overview

Read authority first: Lab verdict/status, tradeability, preparation/morning permission, coherence, conflict state and execution lock. Then read canonical direction, phase, intent, tier, regime, score, target plan, positive/negative factors and sector. Overview answers: **what is the idea, is it permitted, and why?**

### Trade Setup

Verify instrument, exact contract, strike, expiry, DTE, quote/liquidity, breakeven, target, invalidation, runway, GEX levels, WBS guidance and hold plan. Strike is not the underlying entry price. A replacement contract must come through governed contract repair.

### Options

- Delta, gamma, theta and vega describe option sensitivities, not certainty.
- Contract IV, ATM IV, IV rank/label, HV and IV/HV compare implied and realised volatility.
- Term structure, theta drag and vega risk help select tenor/structure.
- Bid, ask, mid, open interest, volume, spread and synthetic-mark status describe execution quality.
- Zero bid, missing quote or excessive spread must not be priced optimistically.

### Convexity

Convexity data state, score and campaign summarise whether volatility/structure conditions support the option. Supporting convexity cannot override a missing contract, failed trigger, execution lock or unknown monetary loss.

### Stage Ladder

Read readiness stage/label, `readiness_enter_now`, expiry/checkpoint fields, hold urgency and hold window. `readiness_enter_now` is evidence about progression; it must agree with current Lab and morning authority before an order is possible.

### Morning Val

This is the trading-day reconciliation: data state, permission, route, lane, entry action, unlock condition, alignment and selected contract. It should explain every downgrade or repair requirement.

### EIL

`eil_signal_verdict`, `eil_v3_verdict` and `eil_composite_eod` explain integrated evidence. They are not independent final authorities. The Lab authority family governs execution.

### Q-OMEGA / GARCH

Forecast realised volatility, IV tailwind, expected moves, confidence, jump-risk flag, method and bars used describe future movement magnitude/volatility value. They do not select CALL versus PUT.

## 10. Current 232-field data contract

The following is the exact current `FINAL_BOOK_FIELDS` inventory, grouped by function. Field names are reproduced verbatim so the GPT user-guide author can map UI labels to production data.

### 10.1 Identity, mode and ranking

`lab_schema_version`, `pipeline_mode`, `run_id`, `ticker`, `trade_idea_id`, `lab_rank`, `priority_rank`, `priority_score`, `notes`, `source_payload_json`.

Use: establish contract version, operating mode, run identity, unique idea, display order and underlying source payload. `source_payload_json` is excluded from the compact triage view but retained in the full governed book for audit.

### 10.2 Lab authority, preparation and coherence

`lab_verdict`, `lab_tradeable`, `prep_permission`, `lab_status`, `lab_execution_status`, `eod_candidate_status`, `execution_category`, `action_category`, `campaign_verdict`, `display_execution_mode`, `position_size_display`, `lab_coherence_status`, `lab_coherence_flags`, `execution_lock_reason`, `requires_live_validation`.

Use: decide whether the idea is preparation-only, waiting, repairable, restricted, executable or blocked. Coherence flags and execution locks take precedence over optimistic evidence.

### 10.3 Morning execution and alignment

`morning_execution_permission`, `morning_execution_route`, `morning_execution_lane`, `morning_entry_action`, `morning_unlock_condition`, `morning_lab_alignment_status`, `morning_lab_alignment_reason`, `morning_selected_contract_symbol`, `morning_data_state`.

Use: confirm current trading-day permission, route, lane, required condition, Lab agreement and contract. An unusable or absent morning state cannot satisfy required live validation.

### 10.4 Direction, conflicts and core classification

`canonical_direction`, `conflict_state`, `conflict_flags`, `direction`, `direction_conflict_status`, `direction_conflict_reason`, `phase`, `intent`, `tier`, `regime`, `composite_score`.

Use: understand the governed directional expression and core market classification. Use `canonical_direction` for execution; retain `direction` and conflict fields for traceability.

### 10.5 Contract identity, repair and alternatives

`instrument`, `contract_symbol`, `contract_data_state`, `contract_source`, `contract_repair_status`, `contract_repair_required`, `contract_repair_reason`, `contract_repair_action`, `contract_repair_live_action`, `contract_repair_alternative_used`, `alternative_contract_attempts`, `alternative_contract_1`, `alternative_contract_2`, `alternative_contract_3`, `strike`, `expiry`, `dte`.

Use: identify the exact intended contract and make every repair/alternative explicit. A junior trader must not substitute an alternative unless the governed fields show it was selected and validated.

### 10.6 Contract price, liquidity and research routing

`premium_mid`, `spread_pct`, `liquidity_score`, `options_research_route`, `options_research_permission`, `contract_bid`, `contract_ask`, `contract_mid`, `contract_oi`, `contract_volume`, `contract_mark_synthetic`, `options_score`.

Use: determine whether the assessed contract is liquid and how its price was obtained. A synthetic mark is diagnostic evidence, not equivalent to an executable quote.

### 10.7 Explanation and sector classification

`entry_reason`, `positive_factors`, `negative_factors`, `sector`, `gics_sector`, `gics_sector_norm`, `sector_etf`.

Use: explain the setup and its headwinds, and map the ticker to governed sector context. Negative factors must remain visible even when the idea is highly ranked.

### 10.8 Risk/reward and EV3

`rr_predicted`, `rr_underlying`, `rr_premium_expected`, `ev_predicted`, `ev3_data_state`, `ev3_status`, `ev3_reason_code`, `ev3_reason_detail`, `ev3_absolute_state`, `ev3_shadow_only`, `ev3_structure`, `ev3_state_match_type`, `ev3_state_similarity`, `ev3_n_effective`, `ev3_p_target`, `ev3_p_stop`, `ev3_p_timeout`, `ev3_ev_conservative_return`, `ev3_ev_lower_bound_return`, `ev3_uncertainty_total_return`, `win_prob_predicted`.

Use: keep underlying geometry separate from option-premium economics; read EV state, sample/effective observations and uncertainty as well as the headline number. `ev3_shadow_only` means EV3 is evidence, not permission authority.

### 10.9 Actuarial and behavioural matching

`actuarial_match_method`, `actuarial_match_type`, `actuarial_ev_weight`, `behaviour_state_key`, `behaviour_state_hash`, `actuarial_sample_size`, `actuarial_confidence`, `win_rate_source`.

Use: establish how comparable historical evidence was found, its sample/confidence and its influence. Exact/high-sample evidence deserves more weight than fallback or sparse matches.

### 10.10 Catalyst evidence

`catalyst_overlay`, `catalyst_type`, `catalyst_date`, `catalyst_truth_score`, `catalyst_direction_bias`, `catalyst_event_status`.

Use: identify scheduled/unscheduled event context, strength and directional relevance. It adjusts risk awareness and timing; it is not permission by itself.

### 10.11 Market physics

`physics_state_id`, `hidden_state_label`, `state_transition_label`, `market_energy_score`, `compression_energy`, `directional_force`, `force_alignment_score`, `trend_inertia`, `entropy_score`, `phase_transition_probability`, `liquidity_friction_score`.

Use: understand whether energy, force, persistence, transition probability and liquidity support the thesis. These are model states, not broker-order instructions.

### 10.12 Macro and EIL

`macro_regime`, `sector_tilt`, `regime_drift_status`, `macro_data_role`, `eil_signal_verdict`, `eil_v3_verdict`, `eil_composite_eod`.

Use: macro provides sector/regime context and EIL summarises evidence. `macro_data_role` should make the advisory role explicit. Neither family replaces Lab execution authority.

### 10.13 Entry, invalidation, target and price lineage

`entry_plan`, `invalidation_price`, `target_price`, `target_in_play`, `structural_target`, `underlying_price`, `signal_price`, `scanner_price`, `target_zone`, `runway_to_target`, `runway_to_wall_pct`, `breakeven_price`, `breakeven_pct`, `breakeven_feasibility`, `option_gain_at_target`.

Use: reconstruct the assessed price state and determine trigger-to-target geometry, invalidation, runway, breakeven feasibility and potential option gain. Differing price fields must be timestamp/source coherent.

### 10.14 Layer-2 outcome estimates

`layer2__raw_prob_target_hit`, `layer2__adjusted_prob_target_hit`, `layer2__raw_expected_time_to_target`, `layer2__outcomes__median_days_to_target`.

Use: compare raw and adjusted target-hit estimates and expected/median time. These values help assess whether the contract DTE and hold plan are plausible; they are not guarantees.

### 10.15 Greeks and volatility

`contract_delta`, `contract_gamma`, `contract_theta`, `contract_vega`, `contract_iv`, `iv_rank`, `ivp_label`, `atm_iv`, `hv_30d`, `iv_vs_hv`, `term_structure`, `theta_drag_pct`, `vega_risk_pct`, `theta_constrained`.

Use: assess directional sensitivity, convexity, daily decay, volatility exposure, relative volatility price and tenor. Confirm units and annualisation before comparisons.

### 10.16 GEX and gamma structure

`call_wall`, `put_wall`, `gamma_flip`, `max_pain`, `pcr_signal`, `gamma_island_on_path`, `gamma_island_level`, `gamma_island_distance_pct`.

Use: locate potential ceiling/floor, regime flip, pinning and gamma-island path risk. These levels inform structure; they are not guaranteed barriers.

### 10.17 Wall Break Score

`wbs`, `wbs_grade`, `wbs_wall_price`, `wbs_wall_dist_pct`, `wbs_f5_momentum`, `wbs_phase_b_trigger`, `wbs_phase_c_trigger`, `wbs_entry_guidance`, `wbs_size_guidance`, `wbs_wall_stall_rule`, `wbs_notes`, `wbs_pcr_volume_state`, `wbs_data_state`, `wbs_break_direction`, `wbs_momentum_alignment_state`.

Current grades: `IMMINENT` at 75 or above, `PROBABLE` from 55 to below 75, `POSSIBLE` from 35 to below 55, and `UNLIKELY` below 35. Use WBS to rank wall-break evidence and read its data/momentum states. Missing PCR volume receives no favourable bonus.

### 10.18 Convexity, readiness and time-stop plan

`convexity_data_state`, `convexity_score`, `convexity_campaign`, `readiness_stage`, `readiness_label`, `readiness_enter_now`, `ts_expiry_date`, `ts_dte_remaining_at_stop`, `ts_checkpoint_date`, `ts_checkpoint_rule`, `ts_dte_used`, `hold_urgency`, `scenario_dte_target`, `hold_window`, `time_horizon`, `hold_period`.

Use: understand option-convexity support, campaign progression, checkpoint/expiry relationship and intended hold. `readiness_enter_now` cannot override a false `lab_tradeable`, missing morning permission or execution lock.

### 10.19 Trigger and veto control

`trigger_price`, `trigger_price_source`, `trigger_evidence`, `trigger_primary`, `trigger_quality`, `trigger_score`, `trigger_codes`, `trigger_data_state`, `hard_vetoes`, `options_hard_vetoes`, `advisory_flags`.

Use: verify when the idea becomes actionable, which price/source supports it and whether a hard prohibition exists. Advisory flags inform judgement; hard vetoes prevent entry.

### 10.20 GARCH / Q-OMEGA

`garch_data_state`, `garch_method`, `garch_forecast_vol`, `garch_iv_tailwind_score`, `garch_jump_risk_flag`, `garch_forecast_confidence`, `garch_expected_move_1_5d`, `garch_expected_move_6_10d`, `garch_expected_move_11_20d`, `garch_price_bars_used`.

Use: assess forecast realised volatility, volatility-value tailwind, jump risk, expected movement by horizon and model sufficiency. It does not set direction.

### 10.21 Data quality, provenance and PCR-volume state

`data_quality_flags`, `field_provenance_json`, `pcr_vol_status`, `pcr_vol_missing_reason`, `pcr_vol`.

Use: understand field lineage, material defects and whether PCR volume is available. A missing PCR state must remain missing and must never create a positive score implicitly.

## 11. Missing-data and display semantics

The current screenshots contain blank/dash values and malformed characters. The finished UI and user guide must use explicit states:

| State | Meaning | Trading consequence |
|---|---|---|
| `AVAILABLE` | Governed value exists and passed validation | Use with its source/time/unit |
| `STALE` | Value exists but exceeds its freshness rule | Revalidate before entry |
| `NOT_APPLICABLE` | Metric does not logically apply | No penalty unless strategy requires it |
| `NOT_EVALUATED` | Producer did not/could not calculate it | Review or block according to criticality |
| `MISSING_DATA_DEFECT` | Required data should exist but is absent | Repair/block |
| `NEUTRAL` | Model ran and genuinely returned neutral | Treat as neutral evidence |
| `ZERO` | Calculation genuinely returned zero | Use as a real value, never as missing |

Encoding corruption such as the mojibake and replacement glyphs shown in the screenshots is a display/data-contract defect. It must not be interpreted as a permission, percentage, direction, price or reason.

## 12. Junior trader standard operating procedure

### Step 1 — Prove run integrity

- Confirm the current intended `run_id`, `pipeline_mode`, `lab_schema_version` and governed browser source.
- Confirm the row has a stable `trade_idea_id` and usable source payload/provenance.
- If the Lab cannot prove the row's origin, do not trade it.

### Step 2 — Prove authority

- Read `lab_verdict`, `lab_tradeable`, `prep_permission`, `lab_execution_status`, coherence, conflict and lock fields.
- If live validation is required, confirm the morning authority and alignment fields.
- The safest state wins whenever labels disagree.

### Step 3 — Explain the thesis

- State ticker, canonical direction, phase, intent, regime and horizon.
- State in one sentence what should move, in which direction, over what period, and why now.
- Identify trigger, invalidation, target and time constraint.

### Step 4 — Verify the contract

- Match contract symbol, type/instrument, strike and expiry at the broker.
- Confirm DTE covers the hold window and event risk.
- Check bid, ask, mid, spread, liquidity, OI, volume and synthetic-mark status.
- Never perform an ungoverned replacement when repair is required.

### Step 5 — Verify economics and monetary risk

- Keep `rr_underlying` separate from `rr_premium_expected`.
- Read EV3 state, reason, probabilities, uncertainty and shadow status—not only one number.
- Confirm multiplier, quantity, planned limit, total debit and maximum loss.
- Under the current contract, obtain supervising-trader confirmation for the missing canonical monetary-ticket fields.

### Step 6 — Read supporting evidence

- Actuarial/behaviour: historical comparable-state quality.
- Market physics/EIL: mechanism, integration and contradictions.
- GEX/WBS: walls, path risk and break quality.
- GARCH/Q-OMEGA: volatility magnitude/value and horizon.
- Catalyst/macro: event and sector context.
- No advisory layer overrides a control failure.

### Step 7 — Place the exact order

- Use only the approved contract, limit, quantity and risk.
- Do not chase a restricted limit or enlarge a probe.
- Recheck total monetary debit/maximum loss before submission.
- Record order time, limit, fill and fees.

### Step 8 — Manage and close

- Monitor invalidation, target, wall, checkpoint, time stop, DTE and liquidity.
- Apply the planned scale-out/exit rule.
- Record all partial exits, final exit, reason and realised outcome.

## 13. Mandatory escalation

A junior trader must not place an order when:

- run/source lineage is not proven;
- live validation is required but morning data is absent, stale or misaligned;
- Lab tradeability, execution status and morning permission disagree;
- direction is unresolved or a hard conflict/veto/lock exists;
- contract identity, bid/ask, DTE or liquidity is defective;
- governed contract repair remains outstanding;
- multiplier, quantity, limit or maximum loss is unknown;
- trigger, invalidation or target is missing or directionally inconsistent;
- current quote materially changes the assessed economics;
- event timing conflicts with the hold/expiry plan;
- a control field contains malformed text or unexplained units;
- readiness says enter now while authority says wait/validate/repair;
- the trader cannot explain the thesis and exit condition clearly.

## 14. CRWV screenshots: historical training example only

The supplied screenshots demonstrate why the authority hierarchy matters. CRWV showed a PUT thesis, a contract, positive premium RR, volatility and GEX evidence, while also showing morning validation required, review-only sizing, missing/corrupted values and a stage ladder implying immediate entry.

Correct reading:

- the thesis and evidence may be reviewed;
- morning validation and zero/review sizing prohibit a live order;
- stage readiness cannot grant execution permission;
- corrupt trigger/momentum/sector/reason values are defects, not neutral support;
- a complete monetary-risk ticket is required before entry.

This is an interface example, not a current CRWV recommendation.

## 15. Validated reference baseline

The hardened reference run reviewed immediately before this document was `20260824_220616`:

- 1,063 governed final candidates;
- 232 governed fields;
- zero duplicate trade-idea identifiers;
- zero source errors;
- zero false EOD enter-now states;
- 49 candidates with authoritative WBS coverage: 5 imminent, 24 probable and 20 possible;
- CRWV reconciled to WBS 51.9 / `POSSIBLE` after removal of a favourable legacy bonus for missing PCR;
- browser loaded the governed v2 source.

This is a test/reference baseline, not a guarantee for later runs. Every run needs its own integrity summary.

## 16. Functionality and data roadmap

### IL-1 — Complete the governed execution ticket (highest priority)

Add canonical fields and validation for:

- contract multiplier and adjusted-contract flag;
- proposed limit and quote age;
- approved/recommended quantity;
- planned debit/credit;
- maximum loss and maximum profit where defined;
- account-risk percentage and risk-budget source;
- prominent invalidation, target and time stop;
- order-verification confirmation.

Acceptance:

- every tradeable row has all strategy-required numeric fields;
- monetary arithmetic reconciles to legs and multiplier;
- missing/stale ticket fields remove tradeability;
- adjusted contracts cannot inherit an assumed standard multiplier;
- tests cover long calls, long puts and debit spreads.

### IL-2 — Simplify the UI without deleting evidence

- Put an execution card first: authority, direction, contract, limit, quantity, maximum loss, trigger, invalidation, target and time stop.
- Keep one execution authority; label model verdicts as evidence.
- Move secondary analytics/provenance into expandable panels.
- Replace ambiguous blanks/dashes with governed missing states.
- Enforce UTF-8 end to end and eliminate malformed glyphs.

Acceptance: a trained junior can decide execute, wait, repair or block without opening raw files and can explain why.

### IL-3 — Freshness and data-quality service

- Define family-specific freshness rules for quote, morning, GEX, macro, catalyst and historical evidence.
- Display source, as-of time, age and state.
- Block only when a control-critical field is defective/stale.
- Enforce `NOT_APPLICABLE`, `NOT_EVALUATED`, `MISSING_DATA_DEFECT`, `NEUTRAL` and `ZERO` semantics.
- Publish a run-level completeness and reconciliation report.

### IL-4 — Governed manual-order confirmation

- Tie the intended broker order to `trade_idea_id` and run.
- Capture broker/account risk tier, order type, limit, quantity, time and approval.
- Compare the proposed order with the assessed contract.
- Log deviations and supervisor approval.

This phase need not automate a broker. It makes manual execution controlled and auditable.

### IL-5 — Position-management cockpit

- Link open positions to their original idea and run.
- Refresh underlying, option mark, spread, days held, DTE and P&L.
- Track invalidation, target, wall, checkpoint, time stop and event countdown.
- Record scale-outs, stops, exits and reasons.
- Prevent a new signal from silently rewriting an existing trade plan.

### IL-6 — Monetisation and learning analytics

- Link every submitted/opened/closed trade to signal, contract and actual fills.
- Measure win rate, profit factor, return distribution, drawdown, time to profit/loss and profitable-close rate.
- Segment by authority state, direction, strategy, WBS, actuarial match, volatility state, sector and horizon.
- Separate model quality from manual slippage/execution.
- Use walk-forward/out-of-sample validation and prevent train/test leakage.
- Report calibration, sample size and uncertainty.

### IL-7 — Optional decision/event database (later)

A future operational database can store immutable runs, canonical ideas, time-versioned evidence, quotes, contract-selection events, morning decisions, human approvals, orders, fills and outcomes.

Benefits: simpler Lab queries, historical reconstruction, auditability, fewer file joins and a clean feedback loop. Costs: migration, reconciliation, backup, retention and transactional controls. Build it after the current final-book contract and IL-1 execution ticket are stable; it is not required to correct today's display.

## 17. Roles

### Junior trader

Follows permission/checklists, verifies exact order and monetary risk, does not override repair/block states, records execution/outcome, and escalates contradictions.

### Supervising trader

Approves quantity/account risk under current limitations, reviews exceptions and event exposure, and coaches entry/exit discipline.

### Pipeline operator

Runs evening/morning workflows, verifies completion and final-book commit, retains run evidence, and never manually edits governed rows.

### Engineering/data owner

Owns schema, lineage, units, tests, migrations, reproducibility, backup and publication of contract changes.

## 18. Prompt instructions for GPT user-guide production

When this document is uploaded, instruct GPT to:

1. Write in British English and plain trading language.
2. Separate current production, current limitations and roadmap functionality.
3. Use the exact 232-field names in Section 10; do not invent fields or thresholds.
4. Treat the final opportunity book as the only governed signal source.
5. Explain macro, EV3, actuarial, physics, EIL, GEX/WBS and GARCH as distinct advisory layers.
6. State that valid morning authority is required wherever live validation is flagged.
7. State that the current junior workflow is supervised for quantity and monetary risk.
8. Include the permission hierarchy, numeric-ticket checklist, eight-step SOP and escalation list.
9. Use CRWV only as a historical interface example, never a recommendation.
10. Add screenshot placeholders for Triage, Overview, Trade Setup, Options, Convexity, Stage Ladder, Morning Val, EIL and Q-OMEGA.
11. Explain visible fields using: definition, producer, timing, unit, interpretation, authority, missing-data behaviour and trader action.
12. Include options-risk disclosure: options may expire worthless; spreads have liquidity, assignment and exercise risks; model outputs are uncertain.
13. Never promise accuracy, profit or autonomous execution.
14. Teach users to inspect the full ticket and negative evidence rather than chase the highest score.

Suggested guide chapters:

1. What AVSHUNTER and the Intelligence Lab do
2. Daily evening-to-morning cycle
3. Permission and authority
4. Triage workflow
5. Each Intelligence Lab tab
6. Models and evidence
7. Exact order-verification checklist
8. Monitoring and exits
9. Missing/stale/conflicting data
10. Worked examples
11. Escalation and troubleshooting
12. Glossary and risk disclosure

## 19. Final operating statement

The Intelligence Lab should be the single place from which a user understands and executes a governed AVSHUNTER trade. Its purpose is not to maximise green signals. It must preserve evidence, resolve authority, expose defects, bound monetary risk and make the intended trade reproducible.

Today the Lab can act as the governed signal-review cockpit. Full unsupervised junior execution should wait for IL-1, the complete numeric execution ticket and its blocking controls. Until then, signal authority, direction, contract and evidence can be used within a validated run, while quantity and maximum monetary risk require explicit supervised confirmation.
