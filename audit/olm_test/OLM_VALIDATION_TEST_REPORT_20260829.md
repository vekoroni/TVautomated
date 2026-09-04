# AVSHUNTER OLM Validation & Full-Pipeline Regression Test Report

**Date:** 2026-08-29 | **Pack ID:** AVS-OLM-TEST-001-EXEC-CC
**Status:** Test-and-report complete. No fixes applied. No production trades, config, thresholds, or live database writes beyond OLM's own pre-existing delivery.

## Reference-standard substitution (read this first)

The task brief cites "AVSHUNTER Options Liquidity Maturation Enhancement Design (Sections 1–19)" as the reference spec. **A full repo search found no such document.** Only `docs/OPTIONS_LIQUIDITY_MATURATION_IMPLEMENTATION_20260829.md` exists — a compact implementation record with topic headers, not numbered sections, and no formulas. The user was asked directly and approved proceeding with: **`docs/OPTIONS_LIQUIDITY_MATURATION_IMPLEMENTATION_20260829.md` + the code's own docstrings/constants as the reference standard.** Every "Design reference" citation below points to that record's section headings plus code file:line — never to a "§8" / "§16" / "§17" style citation, because no document with that numbering was ever located. This report tests **code vs. implementation record**, not code vs. the original enhancement design. Treat this as a materially adequate but narrower evidence base than the brief originally assumed.

**A second scope correction, discovered during testing (Agent 4):** of the 8 files the brief listed as "OLM-touched" (based on their presence in the pre-change backup directory), byte-diff against those backups shows **only 5 were actually modified**: `contracts/lab_control.py`, `eod_candidate_engine.py`, `intelligence-lab/static/index.html`, `morning_gate.py`, `scripts/avshunter_options_intelligence.py`. **`execution_gate.py`, `intelligence-lab/intelligence_lab.py`, and `intelligent_orchestrator.py` are byte-identical to their backups** — they were backed up as a precaution but never actually changed. This fact directly explains the report's single most important finding below (TC-07).

**A third fact governing this whole report:** all OLM code was modified today between 18:33 and 19:26 — **after** the only full pipeline run on disk (`data/output/runs/20260829_100803/`, completed 11:43) and after the production CDS database's last write (`data/canonical/control_plane.sqlite`, 11:19). **No OLM-active full pipeline run exists anywhere.** Every figure below that requires "OLM-active" evidence was obtained either by targeted, code-executed replay against saved artifacts (tagged `TEST_OLM_*`, written outside production paths) or is explicitly marked BLOCKED where that wasn't possible without live provider calls or a fresh ~1.5h production run — neither of which any agent was authorized to launch unilaterally.

---

## 1. Implementation Status — OLM-0 through OLM-10

No canonical "OLM-0…OLM-10" phase list exists in either the implementation record or the code (no `OLM-N` tags found anywhere in the repo). The mapping below is this report's own construction from the implementation record's "Governed flow" 10-item list, with OLM-0 added as the foundational lifecycle-contract module the other 10 steps depend on. Status is BUILT / PARTIALLY BUILT / NOT BUILT, with the evidence that determined it.

| Phase | Description | Status | Evidence |
|---|---|---|---|
| **OLM-0** | Foundational lifecycle contract: three-way separation (thesis validity / contract executability / maturation-monitoring worth), deterministic non-probability scoring | **BUILT** | `contracts/options_liquidity_lifecycle.py` (646 lines), `canonical_data/option_liquidity_lifecycle.py` (1042 lines) — both new files (no pre-change backup exists for either, confirming net-new). Agent 1: 36/36 formula tests pass, all state/boundary sweeps correct. Agent 3 Tests A1/A2: three-authorities separation executes correctly in both directions. |
| **OLM-1** | Options Intelligence receives only the CDS-authorised post-filter ticker worklist | **BUILT** | Wiring confirmed in `scripts/avshunter_options_intelligence.py` diff (506 lines added) and Agent 3's fetch-governance tests (C2). Not exhaustively tested for the specific "post-filter worklist" gating language, but the mechanism it depends on (`should_fetch`/`active_monitor_worklist`) is executed and correct. |
| **OLM-2** | Same-session canonical MarketData chain resolution before provider call | **BUILT** | Agent 3 Test B4 (PASS) — `fetch_chain()` resolves MarketData/CDS before any Polygon path; confirmed by direct code read of the resolution order. |
| **OLM-3** | Missing-chain acquisition + CDS write-through; Polygon options prohibited | **BUILT** | Agent 3 Test B4 (PASS) — Polygon options guard confirmed intact (this guard predates OLM; OLM added corroborating telemetry, did not weaken it). |
| **OLM-4** | Chain retains zero/low-OI strikes; OI/volume are a ranking feature, not an acquisition or thesis-deletion gate | **PARTIALLY BUILT** | Core classifier (`classify_current_executability`) has **no OI/volume parameter at all** — confirmed by signature inspection (Agent 1 Test I, Agent 2 TC-03/TC-04, both PASS). **But** `select_repair_alternative_contracts()` (the contract-family neighbour-selector) hard-gates on `open_interest>=50` and `volume>=1` — directly contradicting this principle (Agent 2 TC-08, **FAIL**, reproduced with 3 controlled variants). |
| **OLM-5** | Long CALL/PUT selector: DTE, delta, moneyness, target reachability, calculable mark | **BUILT** at the lifecycle-classifier level | Agent 1 Tests A1/A2/B1-B14/C (PASS, exhaustive boundary sweep). Same OLM-4 caveat applies to the separate repair-alternative selector. |
| **OLM-6** | Quote-quality classification: executable / reviewable / pending / stale / zero-bid / no-market / terminally unsuitable | **BUILT** | Agent 1 Test B1-B14 — all 14 constructed boundary cases (spread at exactly 18.0%/25.0%, freshness at exactly 900s, DTE at exactly 10, zero-bid, no-market, no-displayed-size, moneyness-unsuitable, invalid-quote variants) resolved to the exact state the code's branch structure implies. |
| **OLM-7** | EOD handoff: thesis, exact contract, lifecycle state, runway, quote lineage, deterministic 1/2/3-session monitoring scores | **BUILT** | Agent 1 Tests D/E/F/G (PASS) at the module level; Agent 4 Test A1 confirms `eod_candidate_engine.py` diff (43 lines) adds the branch and 21 OLM passthrough fields. The branch is present but inert against the only saved run (pre-OLM data) — expected, not a defect, since no OLM-active run exists. |
| **OLM-8** | Morning Gate exact-contract MarketData refresh; replacement OCC symbol is a new economic object requiring full repricing | **BUILT** | Agent 2 TC-09 (PASS, executed — `economics_recomputed=False` raises `DatasetValidationError`, field diff confirms old contract's premium/Greeks never carried over) and TC-11 (PASS — morning live quote sourced exclusively from `live_data`, never EOD placeholders). |
| **OLM-9** | Morning Gate appends thesis events, exact-contract observations, selection events to `control_plane.sqlite` (append-only) | **BUILT** (mechanism), **NOT YET EXERCISED IN PRODUCTION** | Agent 3 Test C1 (PASS, executed against isolated tmp DB copy — table creation, idempotent replay, distinct-event append, terminal-state block all confirmed) and Test C3 — the production DB does not yet contain these tables, confirmed by direct live query, but this is explained: tables are lazily created (`CREATE TABLE IF NOT EXISTS`) on first OLM-active write, feature flags are armed in `run_evening.bat`/`run_premarket.bat` (`AVSHUNTER_CANONICAL_DATA_ENABLED=1`, `AVSHUNTER_CANONICAL_WRITE_THROUGH=1`), and simply no governed run has executed since OLM code landed. |
| **OLM-10** | Intelligence Lab displays lifecycle/lineage fields; fails closed on `CONTRACT_REPRICE_REQUIRED`; never infers permission from a maturation score | **PARTIALLY BUILT** | Agent 4 Test A1 (PASS) — governed book expanded 297→329 fields, additive, order-preserving, all 14 doc-listed field concepts present. Test A2 (PARTIAL) — 20/32 new fields rendered in the UI with zero dead-name drift, but 12/32 are not surfaced, **including both explicit non-authority disclosure fields** (`maturation_score_is_probability`, `maturation_execution_authority`). The `CONTRACT_REPRICE_REQUIRED` fail-closed claim itself holds (`contracts/lab_control.py:2119`, confirmed by Agent 2's TC-05 investigation) — **but this narrow claim is the full extent of the safety net**, and it does not extend to `THESIS_INVALIDATED` or any other non-executable OLM state, which is exactly what allows the report's most serious finding below. |

**Summary:** 7 of 11 phases fully BUILT, 3 PARTIALLY BUILT (OLM-4/5's repair-selector gap, OLM-9's not-yet-exercised production tables, OLM-10's incomplete UI coverage), 0 NOT BUILT. No test below is marked BLOCKED for "phase not built" reasons — every phase has at least a working core mechanism.

---

## 2. Test Cards — Agent 1: Formulas and Classification Logic

**Top-level pytest result:** `venv/Scripts/python.exe -m pytest tests/test_options_liquidity_lifecycle.py tests/test_option_liquidity_lifecycle.py -v` → **36 passed, 0 failed** (18.85s): 27 from `test_options_liquidity_lifecycle.py`, 9 from `test_option_liquidity_lifecycle.py` — exactly matching the implementation record's "Core lifecycle calculations: 27 passing tests" and "Morning/CDS append-only integration: 9 passing tests" claims, independently re-verified by execution, not taken on faith.

### Test: A1 — Delta-band / moneyness-treatment boundaries
- **Design reference:** implementation record "Intelligence Lab fields"; `contracts/options_liquidity_lifecycle.py:153-167`
- **Method:** `classify_moneyness("CALL", spot=100, strike=100, delta=<8 boundary values>)`
- **Actual result:** 0.19→FAR_OTM_LT_020/REJECT_FAR_OTM; 0.20→DEVELOPING_OTM/MONITOR_OTM_MATURATION; 0.349999→DEVELOPING_OTM; 0.35→NEAR_ATM/PREFERRED_EXECUTION; 0.60→NEAR_ATM; 0.600001→ITM_060_075/REVIEW_ITM_STOCK_REPLACEMENT; 0.75→ITM_060_075; 0.750001→DEEP_ITM/OUTSIDE_DEFAULT_CONVEXITY_MANDATE — every boundary exactly matches the code's `<`/`<=` operators.
- **Verdict:** PASS | **Test confidence:** High (executed).

### Test: A2 — ATM tolerance boundary (0.50%) and delta/moneyness consistency flag
- **Design reference:** `contracts/options_liquidity_lifecycle.py:142-147,169-174`
- **Method:** `classify_moneyness` across strikes 99.49–100.51; `delta=0.70` at a 10%-OTM strike.
- **Actual result:** strike=100.50→ATM, 100.51→OTM, 99.50→ITM, 99.51→ATM (asymmetric `<`/`>` operators, both sides confirmed independently). Inconsistency case: `moneyness_state=OTM, absolute_delta=0.70 → delta_moneyness_consistent=false`.
- **Verdict:** PASS | **Test confidence:** High.

### Test: B1–B14 — `classify_current_executability` full state/boundary sweep
- **Design reference:** "Governed flow" step 6; `contracts/options_liquidity_lifecycle.py:258-386`
- **Method:** 14 constructed calls: spread at exactly 18.0% → EXECUTABLE_NOW; 18.1818% → REVIEWABLE_SPREAD; 24.998906% → REVIEWABLE_SPREAD (`<=` inclusive confirmed); 33.33%→LIQUIDITY_PENDING; freshness age=900s exactly → still EXECUTABLE_NOW; 901s → QUOTE_STALE (`age > limit` strict, confirmed); ZERO_BID; NO_CURRENT_MARKET; NO_DISPLAYED_SIZE vs. same-with-sizes → EXECUTABLE_NOW; DTE=9.999<10→DTE_UNSUITABLE, DTE=10==10→passes; MONEYNESS_UNSUITABLE; NO_LISTED_MARKET; 3× INVALID_QUOTE variants.
- **Actual result:** every case returned exactly the state the code's branch structure implies. **`execution_authority` is `False` on literally every state including `EXECUTABLE_NOW`**, with `execution_authority_reason="QUOTE_STATE_ONLY_NO_CAPITAL_AUTHORITY"` — confirming the "quote state ≠ capital authority" claim as an emitted field, not prose.
- **Verdict:** PASS on all 14 | **Test confidence:** High.

### Test: C — DTE requirement formula
- **Design reference:** `contracts/options_liquidity_lifecycle.py:88-114`
- **Method:** `calculate_dte_requirement(hold, monitor_sessions, exit_buffer_sessions)` for 4 input sets, hand-computed as `ceil(hold+monitor+exit)`.
- **Actual result:** (5,3,5)→13, (0,3,5)→8, (10.4,3,5)→19, (2.5,3.5,5.5)→12 — all matched hand calc exactly.
- **Verdict:** PASS
- **Finding, not a test failure:** `scripts/avshunter_options_intelligence.py:4413` contains a **second, different** DTE formula (`math.ceil(hold_sessions * 7/5) + 3`) inside a different function (`_ev3_long_single`), separate from the governed lifecycle path at line 4277 which correctly calls the tested formula. Two DTE formulas exist in the codebase for different purposes — not itself a defect in the OLM contract module, but a dual-formula surface worth follow-up. Test confidence: High for the contract module; Medium (code-read only) for this discrepancy.

### Test: D — Runway/transition-precedence states
- **Design reference:** "Transition precedence" 1–4; `contracts/options_liquidity_lifecycle.py:389-450`
- **Method:** `classify_remaining_runway("CALL", ...)` across 7 constructed combinations.
- **Actual result:** THESIS_INVALIDATED, MOVE_ALREADY_REALIZED, WAIT_FOR_PULLBACK, GAP_CONFIRMATION_EXTENDED, GAP_CONFIRMATION_WITH_RUNWAY, THESIS_UNDER_PRESSURE, THESIS_ACTIVE all produced correctly, `thesis_move_consumed_factor` matching hand arithmetic in every case.
- **Verdict:** PASS | **Test confidence:** High.

### Test: E — `atm_distance_sigma` / `reach_score` formula
- **Design reference:** `contracts/options_liquidity_lifecycle.py:189-231`
- **Method:** `calculate_expected_move_features("CALL", spot=100, strike=105, forecast_vol_annual=0.30, horizon_sessions=1)`, hand-computed `expected_move_pct=vol*sqrt(h/252)`, `atm_distance_sigma=log(strike/spot)/expected_move_pct`, `reach_score=clamp(1-sigma/2)*100`; plus an ITM case to confirm the `max(0, log_distance)` clamp.
- **Actual result:** matched hand calc exactly (`expected_move_pct=1.889822`, `atm_distance_sigma=2.581733`, `strike_reach_score=0.0`); ITM case gave `atm_distance_sigma=0.0`, `strike_reach_score=100.0`. `score_is_probability: false` emitted literally.
- **Verdict:** PASS | **Test confidence:** High.

### Test: F — Maturation scoring / horizon logic + non-authority fields
- **Design reference:** `contracts/options_liquidity_lifecycle.py:463-546`
- **Method:** `evaluate_maturation_horizons(...)` hand-verified against the formula `round(100 * reach_factor * quote_factor * runway, 2)`; also tested `EXECUTABLE_NOW` (expect scores pinned to 100/`ALREADY_EXECUTABLE`) and `thesis_active=False` (expect 0/`NOT_ELIGIBLE`).
- **Actual result:** 1d/2d/3d scores 0.0/4.88/14.26, hand calc matched. `EXECUTABLE_NOW` case → 100.0/`ALREADY_EXECUTABLE` at all horizons. `thesis_active=False` → `NOT_ELIGIBLE_THESIS_OR_RUNWAY`, 0.0. **`maturation_score_is_probability=False` and `maturation_execution_authority=False` confirmed present as literal dict keys on every call**, by direct key access.
- **Verdict:** PASS | **Test confidence:** High.

### Test: G — Composite `evaluate_options_liquidity_lifecycle` end-to-end
- **Design reference:** "Governed flow" steps 5-7; `contracts/options_liquidity_lifecycle.py:574-646`
- **Method:** single composite call with realistic inputs.
- **Actual result:** all sub-evaluator outputs merged correctly into one dict; all non-authority fields present.
- **Verdict:** PASS | **Test confidence:** High.

### Test: H — Frozenset state taxonomy
- **Design reference:** `contracts/options_liquidity_lifecycle.py:40-63`
- **Method:** cross-checked every state produced in Tests B/D against its declared frozenset (`EXECUTABLE_STATES`, `RECOVERABLE_STATES`, `CONTRACT_REPAIR_STATES`, `TERMINAL_STATES`, `MONEYNESS_TREATMENTS`).
- **Actual result:** every state fell in its claimed set.
- **Verdict:** PASS | **Test confidence:** High.

### Test: I — Third spread threshold + `spread_cost_to_expected_profit` ratio
- **Design reference:** task brief's characterization of "spread governance (3 thresholds + a ratio)."
- **Method:** repo-wide grep (excluding backups) for `spread_cost_to_expected_profit`, `expected_profit`, `profit_ratio`, spread-ratio patterns across all OLM-adjacent files.
- **Actual result:** only **two** spread thresholds exist anywhere in the OLM/long-option code (`LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT=18.0`, `LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT=25.0`, defined once in `contracts/long_option_policy.py:13-14`, re-exported/aliased in two other files). No third threshold, no cost-to-profit ratio calculation exists anywhere.
- **Verdict:** **NOT IMPLEMENTED** — the task brief's premise does not hold against the actual code; this is a negative-result finding from an exhaustive grep, not a defect in what was built.
- **Test confidence:** High that it's absent.

### Test: J — Functional selector probe (zero-OI/zero-volume long CALL retained and selected)
- **Design reference:** implementation record "Regression evidence."
- **Method:** confirmed `classify_current_executability`'s signature has no OI/volume parameter at all (structurally the strongest form of "non-authoritative"), corroborated by a passing existing unit test.
- **Verdict:** **PARTIAL** — the "non-authoritative" half is verified at the classification layer (High confidence). The "functional selector probe... retained and selected" half refers to selector/candidate-scan behavior outside this agent's scope — see Agent 2 TC-08 below, which found the **opposite** result at the repair-alternative-selector layer.
- **Test confidence:** Medium.

---

## 3. Test Cards — Agent 2: Scenarios TC-01 through TC-16

**Baseline check performed first:** existing OLM regression suite (`tests/test_option_liquidity_lifecycle.py`, `tests/test_options_liquidity_lifecycle.py`, `tests/test_options_liquidity_morning_lab.py`, `tests/test_eod_options_research_handoff.py`) — **44/44 passed.**

**Result summary: 13 PASS, 2 FAIL, 1 PASS-with-flagged-side-finding (TC-12), 0 BLOCKED.**

### Test: TC-01 — OTM CALL illiquid EOD → ATM/liquid day 2
- **Method:** `evaluate_options_liquidity_lifecycle` called with day-1 (spot=100, strike=106, delta=0.28, spread ~46%) then day-2 (spot=105.8, delta=0.48, spread ~5%) inputs.
- **Actual:** day1 `LIQUIDITY_PENDING`/OTM/not executable → day2 `EXECUTABLE_NOW`/ATM/executable.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-02 — OTM PUT mirrored lifecycle
- **Method:** mirror of TC-01 (strike=94, invalidation=107, target=85).
- **Actual:** identical pattern, mirrored correctly.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-03 — Low OI, tight fresh quote → executable
- **Method:** `classify_current_executability` with spread=2%, age=10s; confirmed via `inspect.signature` the function has **no OI/volume parameter at all**.
- **Actual:** `EXECUTABLE_NOW`, `executable_now=True`.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-04 — High OI, zero bid → not executable
- **Method:** bid=0/ask=0.55, age=10s.
- **Actual:** `ZERO_BID`, `executable_now=False`.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-05 — Wide-spread contract never receives BUY_NOW/BUY_SMALL
- **Method:** wide-spread quote (43.1% OLM spread → `LIQUIDITY_PENDING`) fed into a full governed-direction row, then through the actual `execution_gate.execution_gate(row)` — the real BUY_NOW/BUY_SMALL authority.
- **Actual:** `final_action=CONTRACT_REPAIR`, reason `COST_DESTRUCTION`.
- **Verdict:** PASS, **with an important caveat**: `execution_gate.py` has **zero references anywhere in the file** to any OLM field (`liquidity_state`, `morning_transition_state`, `executable_now`, `thesis_state` — confirmed by grep). It blocked this fixture only because its own unrelated, independent spread threshold (15%) happened to be numerically tighter than OLM's (18%) — not because it consults OLM state. This coincidental pass is the same gap that causes TC-07's failure below.
- **Confidence:** High for the literal result; Medium for "by design."

### Test: TC-06 — Underlying reaches strike but has consumed most of the target
- **Method:** `classify_remaining_runway` with consumed_factor ≈0.9.
- **Actual:** `MOVE_ALREADY_REALIZED`, `thesis_move_consumed_factor=0.9`, `remaining_runway_factor=0.1` — not a naive "strike reached=go."
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-07 — Underlying moves against thesis → INVALIDATED, monitoring stops — ★ CRITICAL FAIL
- **Design reference:** transition precedence #1 `THESIS_INVALIDATED` (highest precedence); `contracts/options_liquidity_lifecycle.py:427-428,500-509`.
- **Preconditions / fixture:** thesis geometry with invalidation crossed (current_spot=94 vs invalidation=95); separately, a governed-direction row with `morning_execution_permission=GO`, a clean live quote (spread 5.1%), `monetisability_state=MONETISABLE`, and `morning_transition_state=THESIS_INVALIDATED` attached.
- **Method:** `classify_remaining_runway` + `evaluate_maturation_horizons`, then the real `execution_gate.execution_gate(row)`.
- **Expected result:** thesis correctly marked invalidated; "contract monitoring stops" (implementation record, persistence contract section).
- **Actual result:** the OLM lifecycle module itself is correct (`remaining_runway_state=THESIS_INVALIDATED`, `maturation_eligibility=NOT_ELIGIBLE_THESIS_OR_RUNWAY`, `maturation_score_1d=0.0`). **But `execution_gate.execution_gate(row)` — the real, production, capital-authority function — returned `final_action=BUY_NOW`, reason `OK`.** Literal log line: `[TC07] BUY_NOW spread=5.1% d=0.44 iv=35.0%(r50) run=0.00% tgt=4.04% g=UNKNOWN pen=1.00 conv=False warn=['NONE']`.
- **Verdict:** **FAIL — critical.**
- **Evidence:** `execution_gate.py` — zero OLM-field references anywhere in the file (grep-confirmed); its BUY_NOW derivation (`:244-354`) uses only `morning_execution_permission`, `campaign_verdict`, `monetisability_state`, and its own independent live-quote checks. `contracts/lab_control.py:2119` only intercepts `CONTRACT_REPRICE_REQUIRED`, never `THESIS_INVALIDATED` — so nothing downstream catches this either. **This is directly explained by Agent 4's scope-correction finding: `execution_gate.py` was never actually modified by OLM** (byte-identical to its pre-change backup) despite being backed up as a precaution.
- **Test confidence:** High — real, reproducible execution of the live production execution-authority function against a thesis OLM has explicitly invalidated.

### Test: TC-08 — Contract-family monitoring selects the liquid neighbour — ★ FAIL
- **Design reference:** "Governed flow" step 4 (OI/volume are ranking, not gates); `scripts/avshunter_options_intelligence.py:4376-4493` (`select_repair_alternative_contracts`).
- **Method:** single-row option chain, tight fresh quote (spread 5%, delta=0.30), varying `open_interest`/`volume` (5/2, 50/2, 0/0).
- **Actual result:** OI=5/vol=2 (tight, fresh) → **0 candidates returned.** OI=50 → 1 candidate returned. OI=0/vol=0 → 0 candidates.
- **Verdict:** **FAIL.**
- **Evidence:** `scripts/avshunter_options_intelligence.py:4466-4469` — `if oi < EV3_MIN_OPEN_INTEREST or volume < EV3_MIN_VOLUME: continue`, thresholds `EV3_MIN_OPEN_INTEREST=50`, `EV3_MIN_VOLUME=1` (`:1114-1115`). Directly contradicts the primary EOD selector (`select_best_contract`, no OI/volume gate) and the pure classifier (no OI parameter at all).
- **Test confidence:** High — reproduced with 3 controlled variants isolating OI as the sole differentiator.

### Test: TC-09 — Replacement contract → full economics recomputation confirmed
- **Method:** `store.record_selection_event(..., economics_recomputed=False)` then `True`, against an isolated tmp CDS DB copy.
- **Actual:** `economics_recomputed=False` raised `DatasetValidationError: replacement contract requires exact economics recomputation`. With `True`: succeeded, and field diff confirmed strike/delta/bid/ask/liquidity_state all changed to the replacement's own values — old contract's fields not carried over.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-10 — Stale quote used as historical context only
- **Method:** `classify_current_executability(quote_age_seconds=3600)`; `store.should_fetch(freshness_seconds=900, now=+14h)`.
- **Actual:** `QUOTE_STALE`, `executable_now=False`; next-morning `should_fetch=True, reason=CANONICAL_OBSERVATION_STALE`; the stale row is still returned as historical context alongside the fetch requirement.
- **Verdict:** PASS | **Confidence:** High for fetch-gating; Medium for the "historical context" framing (accessor doesn't itself re-tag the label stale — callers must and do honor `should_fetch`'s reason).

### Test: TC-11 — Morning live quote overrides EOD context
- **Method:** `morning_gate._morning_liquidity_lifecycle(row, live_data, ...)` with EOD placeholder bid/ask=999.0 that the function never reads, and fresh `live_data` bid/ask=2.30/2.42.
- **Actual:** `bid_used=2.3, ask_used=2.42` — never the placeholder. `EXECUTABLE_NOW`.
- **Verdict:** PASS | **Confidence:** High — `morning_gate.py:1662-1663` sources bid/ask exclusively from `live_data`.

### Test: TC-12 — Deep ITM classified per stock-replacement policy
- **Method:** `classify_moneyness` at delta=0.86 and delta=0.68.
- **Actual:** delta=0.86 → `DEEP_ITM_GT_075`/`OUTSIDE_DEFAULT_CONVEXITY_MANDATE`; delta=0.68 → `ITM_060_075`/`REVIEW_ITM_STOCK_REPLACEMENT` — no lottery-ticket labeling.
- **Verdict:** PASS
- **Side-finding (not executed, flagged Low confidence):** a separate, older code path (`scripts/avshunter_options_intelligence.py:6972-6977`) independently labels delta>0.70 as `"TRAP"` using its own disconnected 0.70 threshold — a second, un-integrated deep-ITM policy alongside OLM's table. Not scored since not executed; worth follow-up.
- **Confidence:** High for the tested claim.

### Test: TC-13 — Phase A/B path never emits a debit spread
- **Method:** `oi_mod.parse_structural_context(row)` — the real production context builder — called for phases A/B/C/D/E (CALL) and one PUT case.
- **Actual:** all returned `('CALL','LONG_CALL')` or `('PUT','LONG_PUT')` — never a spread.
- **Verdict:** PASS | **Confidence:** High — real execution across all 5 phases.

### Test: TC-14 — Terminal ticker generates zero subsequent API requests
- **Method:** thesis transitioned to `INVALIDATED`/`TERMINAL`; `morning_gate._fetch_live_contract` monkey-patched to raise if ever called; ran `_fetch_all_live`.
- **Actual:** zero live option-quote fetch calls; `should_fetch=False, reason=THESIS_INVALIDATED`; empty `active_monitor_worklist`.
- **Verdict:** PASS
- **Caveat:** the underlying equity price fetch is still called unconditionally regardless of thesis termination — outside OLM's documented scope (options-chain governance only), noted for completeness.
- **Confidence:** High.

### Test: TC-15 — CDS returns the identical observation to every consumer
- **Method:** consumer A = `store.latest_observation()`; consumer B = independent raw SQL query against the same DB file; compared.
- **Actual:** identical bid/ask/symbol/`payload_hash` (`7ebd83b7...dddeb52`) from both paths.
- **Verdict:** PASS | **Confidence:** High.

### Test: TC-16 — Intelligence Lab display matches the governed book field names
- **Method:** checked 26 OLM field names referenced in `intelligence-lab/static/index.html` / `AVSHUNTER_sector_ui_patch.js` against `contracts/lab_control.py::FINAL_BOOK_FIELDS`.
- **Actual:** 15/26 fields referenced in `index.html`, all exact-name matches, zero drifted/near-miss names (e.g. `s.liquidity_state`, `s.morning_transition_state` bound literally). `AVSHUNTER_sector_ui_patch.js` has zero OLM references (unrelated sector-focused file). 11/26 governed fields are populated but not rendered anywhere.
- **Verdict:** PASS for the specific defect class tested (no field-name drift recurred). Completeness gap noted separately (superseded by Agent 4's fuller 12/32 count in Section 4 below, which supersedes this narrower 26-field check).
- **Confidence:** High for "no drift"; Medium for completeness (didn't check every dynamic-binding pattern beyond literal `s.<field>` grep).

---

## 4. Test Cards — Agent 3: Three-Authorities Separation, Exclusions, CDS Governance

**Result: 9 of 9 assigned checks PASS.**

### Test: A1 — Contract-authority failure does not invalidate thesis authority
- **Method:** zero-bid contract (contract-side failure) with healthy thesis geometry, executed against both the pure contract module and the real production adapter `_options_liquidity_lifecycle_fields()`.
- **Actual:** `liquidity_state=ZERO_BID`, `execution_authority=False`, but `thesis_state=ACTIVE` (not invalidated).
- **Verdict:** PASS | **Confidence:** High — executed against the actual production adapter.

### Test: A2 — Converse control: thesis-only failure invalidates thesis independent of contract health
- **Method:** thesis geometry crossing invalidation, contract given a tight executable spread.
- **Actual:** `thesis_state=INVALIDATED`, `liquidity_state=EXECUTABLE_NOW` — separation confirmed in both directions.
- **Verdict:** PASS | **Confidence:** High.

### Test: B1 — Straddles/strangles/condors excluded
- **Method:** executed `test_unsupported_multileg_strategy_fails_closed` (raises `ValueError` for non-CALL/PUT); diffed current `scripts/avshunter_options_intelligence.py` vs. its pre-change backup — the backup's docstring and code listed `STRADDLE`/`DEBIT_SPREAD` construction (~lines 4189-4269); current file's docstring reads `LONG_CALL / LONG_PUT` only, and that construction code is **absent**.
- **Verdict:** PASS | **Confidence:** High — executed test + direct diff confirming removal.

### Test: B2 — Automated position sizing unchanged (`pse_final_size` still 0.0)
- **Method:** confirmed `execution_intelligence_runner.py`/`position_sizing_engine.py` absent from the OLM backup list; grepped current `execution_intelligence_runner.py` — hardcoded `0.0` at ~15 sites, no non-zero assignment anywhere.
- **Verdict:** PASS | **Confidence:** High.

### Test: B3 — Macro/EV3 capital authority unchanged
- **Method:** confirmed `scripts/apply_ev3_authority.py`/`vanguard/ev_engine_v3.py` absent from the OLM backup list; read `apply_ev3_authority.py:153` directly.
- **Actual:** `authority_active = False` hardcoded, comment: "EV authority is retired... never convert them into capital permission."
- **Verdict:** PASS | **Confidence:** High.

### Test: B4 — Polygon prohibited for options chains specifically
- **Method:** read `fetch_chain()`/`_fetch_chain_polygon`; confirmed the guard predates OLM (unweakened) and OLM only added corroborating `polygon_options_disabled: True` telemetry.
- **Verdict:** PASS | **Confidence:** High for "not weakened by OLM"; Medium-High for "never called anywhere" (code-read across an 8,229-line file, not exhaustively executed against a live Polygon-returning fixture).

### Test: B5 — No new database
- **Method:** grepped both lifecycle modules and the diffed production file for new `.sqlite`/`sqlite3.connect` literals; traced both production wiring points (`morning_gate.py`, `scripts/avshunter_options_intelligence.py`) to the existing `control_plane.sqlite` path.
- **Verdict:** PASS | **Confidence:** High.

### Test: C1 — Persistence contract: table creation, idempotent replay, distinct-event append, terminal-state block
- **Method:** executed against a fresh isolated tmp DB — wrote an observation, replayed identically, wrote a materially different quote, transitioned to terminal, attempted another observation.
- **Actual:** row count 1 → 1 (identical replay, no duplicate, `reused_existing=True`) → 2 (distinct event). After terminal: `record_contract_observation` raised `DatasetValidationError: cannot observe a terminal thesis`; `should_fetch=(False, "THESIS_INVALIDATED")`; `active_monitor_worklist=()`. Append-only enforcement confirmed via existing test (direct `UPDATE` raises `IntegrityError`).
- **Verdict:** PASS | **Confidence:** High.

### Test: C2 — Fetch governance: fresh observation present → no redundant fetch
- **Method:** `store.should_fetch(...)` with a 10-min-old observation against a 900s freshness window.
- **Actual:** `(False, "FRESH_CANONICAL_OBSERVATION")`.
- **Verdict:** PASS
- **Note:** the pre-existing `api_request_ledger` table (predates OLM, governs whole-chain provider calls) and OLM's own thesis-level `should_fetch` are two correctly-scoped, separate governance layers — not a gap.
- **Confidence:** High for OLM's own layer; Medium for the interaction with `api_request_ledger` (code-read only).

### Test: C3 — Production DB Phase-0 fact re-verified and explained
- **Method:** re-queried `data/canonical/control_plane.sqlite` directly (not taken on the orchestrator's earlier summary).
- **Actual:** confirmed table list (`api_request_ledger, dataset_registry, run_registry, schema_metadata, sqlite_sequence, stage_worklist, ticker_lifecycle`) — no OLM tables present; `schema_metadata` shows only `cds_control_plane_v1` installed 2026-08-22, no `option_liquidity_lifecycle_v1` row. Root cause: `OptionLiquidityLifecycleStore.initialise()` lazily creates tables on first write, gated by feature flags that **are armed** in `run_evening.bat`/`run_premarket.bat` — tables are absent purely because no governed run has executed since OLM landed.
- **Verdict:** PASS (confirmed-absent-as-expected, not a defect) | **Confidence:** High for the mechanism and arming; explicitly not tested/Low confidence for "will actually populate correctly on the next real run" (out of scope — requires a live run).

### Incidental finding (flagged, not scored against OLM)
`tests/test_options_research_contract.py`: 5 of 11 tests FAIL (`hard_vetoes` never populated, `OPTIONS_BLOCKED_ROUTE` never reached under conditions the tests expect). **Verified NOT an OLM regression** — the identical failing scenario reproduces against the pre-change backup. Also flagged: running the full OLM test suite in one `pytest` invocation triggers a Windows stdout-capture crash caused by `scripts/avshunter_options_intelligence.py:87` reassigning `sys.stdout` at import time — not an OLM correctness issue, but affects how future test runs should be invoked (per-file, not batched).

---

## 5. Governed Book & Lab UI Regression (Agent 4, Part A)

### Test: Governed book field additions, order, population
- **Method:** programmatic diff of `FINAL_BOOK_FIELDS` (live module vs. pre-change backup via `importlib`).
- **Actual:** 297 → **329** fields. Zero removed, 32 added, at the identical relative position in both lists (order-preserving, confirmed programmatically). All 14 field concepts from the implementation record's "Intelligence Lab fields" list are present, either as new fields or via `CONTRACT_REPRICE_REQUIRED`'s forced override of pre-existing fields (`economics_comparable=False`, `lab_tradeable=False`).
- **Verdict:** PASS | **Confidence:** High (programmatic diff).

### Test: New fields rendered in the UI (no dead-key recurrence)
- **Method:** diffed `index.html` vs. backup (12 lines added — a new "Liquidity Lifecycle" panel); grepped `AVSHUNTER_sector_ui_patch.js` for all 32 new field names.
- **Actual:** 20/32 new fields referenced in `index.html`, **all character-for-character correct, zero dead/legacy names** — the specific defect class this test targets (recurrence of the prior "159/297 dead legacy field" bug) did **not** recur. But **12/32 new fields are never referenced anywhere in the UI**: `thesis_id`, `thesis_state`, `recovery_disposition`, `minimum_required_dte`, `dte_buffer_sessions`, `maturation_state_1d/2d/3d`, **`maturation_score_is_probability`**, **`maturation_execution_authority`**, `previous_contract_symbol`, `liquidity_persistence_status`, `morning_liquidity_persistence_status`.
- **Verdict:** **PARTIAL** — genuine pass on the specific "no drift" risk, but incomplete: the two fields the implementation record calls out as needing to be **explicit** to the trader (the non-authority disclosure flags) are computed correctly but never surfaced, so a trader has no on-screen confirmation of the "this is not a probability, this has no execution authority" guarantee.
- **Confidence:** High.

### Test: "Plain-language reason" field
- **Method:** searched for a natural-language sentence generator; found none. Constructed a fixture and called the real `evaluate_options_liquidity_lifecycle()` directly.
- **Actual:** the only "reason" outputs anywhere in the OLM code are governed enum codes (`liquidity_reasons: ["ZERO_BID_NOT_EXECUTABLE"]`, `execution_authority_reason: "QUOTE_STATE_ONLY_NO_CAPITAL_AUTHORITY"`, `contract_selection_reason: "NO_LONG_SINGLE_CONTRACT_IN_GOVERNED_DTE_DELTA_RANGE"`). The UI's `displayCategory()` only does `.replace(/_/g,' ')` — cosmetic, not sentence generation. Additionally, `liquidity_reasons` (the most granular reason field) is **not in the governed `FINAL_BOOK_FIELDS` at all**; only `execution_authority_reason` reaches the book, as a low-priority fallback inside the pre-existing `entry_reason` field.
- **Verdict:** **BLOCKED — NOT IMPLEMENTED** as literal natural-language text. Consistent with the rest of the codebase's enum-code convention, but not literal prose.
- **Confidence:** High.

---

## 6. Full-Pipeline Regression Table vs. 29 Aug Baseline (Agent 4, Part B)

All pre-OLM baseline figures were re-verified directly against `data/output/runs/20260829_100803/` artifacts by Agent 4 (not copied from the prior audit doc) — all matched exactly.

| Baseline metric | Pre-OLM value (re-verified) | OLM-touched? | OLM-active value | Deviation reconciled? |
|---|---|---|---|---|
| Package build | 1,527/1,527 built, 0 blocked | N | Unchanged (code untouched) | Yes |
| Vanguard pass rate | 1,482/1,527 (97.1%) | N | Unchanged | Yes |
| Discovery Tier 1 | 18/1,527 (1.2%) | N | Unchanged | Yes |
| Actuarial edge distribution | NEGATIVE_EDGE 944 (61.8%), STRONG_EDGE 98 (6.4%) | N | Unchanged | Yes |
| **Options Intelligence EXECUTE rate** | 81/1,316 (6.2%) | **Y** | **Partially replayed, no live API calls.** Downgrade path (executed, real): replayed all 81 EXECUTE rows through the current `_options_liquidity_lifecycle_fields()` using their own saved contract data — **24/81 (29.6%) downgraded EXECUTE→ARMED** (21 on `REVIEWABLE_SPREAD` 18.4–24.6%, 3 on `REJECT_FAR_OTM`), giving **≤57/1,316 (≤4.3%)** from that population. Recovery path (code-diff confirmed real, but not replayable): OLM also removed the hard OI/volume/spread gate at initial contract selection and widened the delta band — could newly produce a contract for some of the 651 `NO_CONTRACT_PASSED_QUALITY_GATES` drops, but **today's session option chains aren't in the CDS cache** (only 2026-08-28 chains present), so this cannot be tested offline. | **NOT reconciled to a single number.** The **verified half moves the rate down**, contrary to the implementation record's stated purpose ("recovering some of the 651 drops"). The unverified half could move it up. Net direction is genuinely unknown without a fresh live run or live chain replay for the 651 no-contract tickers. Flagged prominently, not asserted either way. |
| Direction Governance suppression | 333 dropped, no governed direction | N — `contracts/direction_governance.py` unmodified (mtime predates OLM, absent from real diff list); consuming gate byte-identical pre/post | Unchanged, re-confirmed at 333 in the same run artifact | Yes |
| GARCH coverage | 1,316/1,316 HAR_RV, 0 fallback | N (`garch_runner.py` untouched) | Unchanged | Yes |
| EOD Candidate Engine | 817/1,527 reaching `morning_candidates` | **Y** — real diff (43 lines: new `liquidity_state` branch + 21 passthrough fields) | **Replayed directly** (`build_candidate_manifest()` re-run against the same saved inputs, output to `TEST_OLM_REGRESSION_20260829/`, no writes to production paths). **Result: 817 rows — exact match.** New branch present but inert against pre-OLM data (expected — `liquidity_state` only populates once Options Intelligence runs OLM-active). | Yes, empirically. One sub-distribution discrepancy (Tier A/B/C mix) traced to a replay-harness gap (`rr_underlying` not reconstructable from saved CSV alone) — explicitly called out as a harness limitation, not an OLM effect; `classify_tier()` itself is byte-identical pre/post OLM. |
| `pse_final_size` | 0.0 for 1,316/1,316 | N | Unchanged, re-confirmed | Yes |
| Governed book field count | 297 | **Y** | **329** | Yes — additive only, reconciled in Section 5. |

**Regression suite corroboration:** 44/44 OLM-specific pytest tests pass; 28/28 adjacent `morning_gate` tests also pass (no collateral regression detected there). A full `pytest tests/` batch run fails at the capture layer for the unrelated reason noted in Section 4 (Windows stdout reassignment) — not an OLM defect.

---

## 7. Overall Verdict: **NOT READY FOR PROMOTION**

### Blocking FAILs (must be resolved or explicitly risk-accepted before the next governed production run)

1. **TC-07 (critical).** `execution_gate.py` — the real, live BUY_NOW/BUY_SMALL capital-authority function, wired into production — has **zero awareness of any OLM field** and will issue `BUY_NOW` for a position whose thesis OLM has already marked `THESIS_INVALIDATED` (the highest-precedence state in the entire transition-precedence design). Root cause confirmed: `execution_gate.py` was **never actually modified** by OLM (byte-identical to its pre-change backup) despite being included in the pre-change backup set. `contracts/lab_control.py`'s fail-closed logic only intercepts `CONTRACT_REPRICE_REQUIRED`, not `THESIS_INVALIDATED` or any other non-executable OLM state, so nothing catches this downstream either. **This is the single most important finding in this report** — it means OLM's own governance can correctly identify a broken thesis and the pipeline can still authorize buying it.

2. **TC-08.** The contract-family repair-alternative selector (`select_repair_alternative_contracts`) hard-gates on `open_interest>=50` and `volume>=1`, directly contradicting the explicit "OI/volume are ranking evidence, not a gate" principle that the core lifecycle classifier correctly implements. This means OLM-4/5's neighbour-selection behavior (TC-08's own scenario) will silently fail to find or select otherwise-valid liquid-but-low-OI replacement contracts.

### Non-blocking but material gaps (should be resolved before claiming full delivery, do not by themselves block promotion)

- **Options Intelligence EXECUTE-rate is unreconciled** (Section 6) — the verified component of OLM's change moves the rate down, not up, contrary to the design's stated purpose; the recovery mechanism is real (code-confirmed) but unmeasured. This needs either a fresh live run or a targeted live-chain replay before the feature's core value proposition can be confirmed either way.
- **12/32 new governed-book fields are not surfaced in the Lab UI**, including both explicit non-authority disclosure flags (`maturation_score_is_probability`, `maturation_execution_authority`) — the exact fields meant to visibly reassure a trader the maturation score carries no authority.
- **No literal "plain-language reason" exists** — all reasoning is governed enum codes, not natural-language sentences.
- **Third spread threshold + cost-to-profit ratio (Test I) does not exist** — the task brief's assumption about this was wrong; flag for whoever specified it, not a code defect.
- **OLM-9's production CDS tables are not yet exercised** — mechanism is correct and flags are armed, but this is unverified in a live production run (expected, given no OLM-active run has occurred).
- Two Low/Medium-confidence side-findings not independently scored: a second, disconnected DTE formula (`scripts/avshunter_options_intelligence.py:4413`) and a second, disconnected deep-ITM policy (`:6972-6977`, `"TRAP"` label at delta>0.70) alongside OLM's own governed tables for the same concepts.
- One incidental, pre-existing (non-OLM) regression in `tests/test_options_research_contract.py` (5/11 failing) — verified not caused by this work, flagged for awareness only.

### What would flip this to READY

At minimum: (1) wire `execution_gate.py` to respect OLM's thesis/liquidity state (or add `THESIS_INVALIDATED`/equivalent to `contracts/lab_control.py`'s fail-closed check, which currently only covers `CONTRACT_REPRICE_REQUIRED`) and re-run TC-07 to confirm it now blocks; (2) either loosen `select_repair_alternative_contracts`'s OI/volume gate to match the documented ranking-only principle, or explicitly document why the repair-selector is intentionally stricter than the primary selector, and re-run TC-08; (3) obtain a real OLM-active Options Intelligence EXECUTE-rate figure (fresh run or live chain replay) and reconcile it against the stated design purpose. No fix was applied to any of these — per the task's explicit instruction, this report identifies and stops.

---

## 8. Git Status Confirmation

`git status --short` was captured immediately before dispatching the four test agents and again at report-consolidation time. **The two snapshots are identical** at the status-line level — no file outside `audit/` changed state (added/modified/removed) as a result of this test task. The only new artifacts are:
- `audit/olm_test/` (this report and Agent 2's test runner/output files — not gitignored, but nested inside the already-untracked `audit/` directory from the prior pipeline-map investigation, so it produces no new status line)
- `data/output/runs/TEST_OLM_REGRESSION_20260829/` (Agent 4's replay outputs — confirmed gitignored via `.gitignore`'s `data/output/` rule, via `git check-ignore -v`)

A stray auto-synced file Agent 4 noted (`pipeline_interpreter/MA_Inputs/pipeline_outputs/morning_candidates_TEST_OLM_REGRESSION_20260829.csv`, written by the EOD engine's own file-sync side effect) was independently re-verified absent at consolidation time — confirmed cleaned up. **No production config, threshold, or database file was modified. No file outside the test-fixture paths above was touched.**

---

## 9. Report Confidence: **Medium-High**

High-confidence components: all formula/classification tests (Section 2), all persistence/exclusion tests (Section 4), the governed-book field-count and order regression (Section 5), and the package-build/Vanguard/Discovery/GARCH/Direction-Governance/`pse_final_size` regression lines (Section 6) — every one of these is an executed result, most cross-corroborated by two independent agents.

What holds this back from High: (1) the reference-standard substitution itself — this report validates code against an implementation *record*, not the original numbered design spec, so any requirement that existed only in the untraceable original document is invisible to this report by construction; (2) the Options Intelligence EXECUTE-rate figure is explicitly unreconciled, the single largest open question in the full-pipeline regression; (3) OLM-9's production persistence tables are verified only against an isolated tmp DB, not a live run; (4) two side-findings (dual DTE formula, dual deep-ITM policy) were flagged but not independently executed/scored. None of these gaps were hidden or silently resolved — each is stated explicitly above with what would be needed to close it.
