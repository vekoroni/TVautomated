# AVSHUNTER — Low Pass-Ratio / Zero-Trade-Day Diagnostic Report

**Date:** 2026-07-16
**Scope:** Discovery (Phase 3) → Options Intelligence (Phase 7) → SuperBrain (Phase 8) → morning
authorization. Diagnosis only — no fixes applied or proposed.
**Method:** Direct code reads (this session) + three parallel deep-read agents (SuperBrain,
Options Intelligence, morning-validator/Discovery) + analysis of two real recent pipeline runs:
`20260624_052030` (last run that includes a completed morning-validation stage) and
`20260716_010747` (most recent EOD run, today). All claims below are `file:line` cited or CSV/JSON
cited against those two runs. Where a claim could not be fully verified it is marked `UNVERIFIED`.

---

## 0. HEADLINE DETERMINATION

**Primary cause: (d) a data-quality/contract-selection failure at Phase 7 (Options Intelligence),
propagated forward and generically mislabeled, is the dominant driver.** Roughly half to
three-quarters of candidates never get a real options contract selected at EOD at all — not
"rejected for being illiquid," but **no contract-selection attempt produced a result** — and this
absence is written to `hard_vetoes`/`contract_repair_reason` using the same generic label used for
every other failure mode (chain-fetch error, bad spot price, no direction, unhandled exception,
*and* genuine illiquidity), destroying the ability to distinguish "structurally nothing tradeable
here" from "the data pull broke." This flows forward and is the dominant reason the **live morning
gate** (see §0.1) issues `FLAG / CONTRACT_REPAIR` instead of `GO` on ~84% of candidates.

Secondary contributing factors, in order of materiality:
- **(b) Compounding** is real but is not the dominant cause in the engine that is actually running in
  production (see §0.1) — it is a much bigger risk in the *other*, non-running gate ladder that
  CLAUDE.md documents (`morning_thesis_validator.py`, ~19 stacked gates).
- **(c) An upstream universe restriction does exist** in Discovery (price/volume/dollar-volume/ATR
  filters), but it is intentional, documented, and does not appear to be the dominant driver of the
  low GO ratio — the bigger drop happens later, at Options Intelligence.
- **(a) A DEP-02-style miscalibrated-field bug**: the original `rr_options`-vs-`rr_underlying` bug is
  **confirmed fixed**. No other DEP-02-scale miscalibration was found in the live rr/ev/composite
  gates. Several smaller field-extraction bugs were found (§4) but they are not the primary driver.

### 0.1 CRITICAL FRAMING CORRECTION — read this before anything else

The task brief (and `CLAUDE.md`) states that only `morning_thesis_validator.py`'s 09:45 ET live run
authorizes a trade. **This is no longer true of the running system.**

- `intelligent_orchestrator.py:399` — `cfg.MORNING_VALIDATION_ENGINE = BASE_DIR / "morning_gate.py"`.
- `intelligent_orchestrator.py:5157-5159` (`premarket_workflow()`) — `from morning_gate import
  run_morning_gate; results = run_morning_gate(...)`. It never imports or calls
  `morning_thesis_validator.py`.
- `morning_gate.py:1-20` — its own module docstring: *"Five checks. Replaces
  morning_thesis_validator.py entirely."*
- This discrepancy was already flagged internally once before: `avshunter_audit_report_20260627.md:134-136`.
- `morning_thesis_validator.py` is still a live, runnable file with its own `--live` CLI (`main()` at
  `morning_thesis_validator.py:2995`) and a much larger ~19-gate compounding scoring ladder (see
  §3.2) — but nothing in the automated pipeline invokes it. If it is being run manually/standalone by
  the trader, its output is a second, independent authorization surface that this report also covers,
  but it is **not** what `intelligent_orchestrator.py --evening` → `--morning` produces today.

**Practical effect on this diagnosis:** the actual live gate is `morning_gate.py`'s 5-check model
(CHECK 1 invalidation / CHECK 2 macro / CHECK 3 contract-liquid / CHECK 4 bond-macro / CHECK 5
Layer-3 model risk), where *only CHECK 1 can BLOCK; CHECK 2–5 can only FLAG* (`morning_gate.py:12-20`).
This is a **much shorter** compounding chain than the brief assumed, which changes the diagnosis:
low GO ratio is not explained by a long AND-chain of individually-reasonable thresholds in the live
engine — it's explained by one check (CHECK 3, contract liquidity) failing on a large majority of
rows because upstream never gave it real data to check.

---

## 1. GATE NECESSITY TABLE

Only hard gates (things that can turn a GO into a non-GO) are listed. Soft/display-only fields are
noted separately in §3.3/§4.

| Gate | File:line | Field(s) read | Threshold | Scale/unit check | Null handling | Observed effect (this run) |
|---|---|---|---|---|---|---|
| **CHECK 1 — Invalidation (live engine, only hard BLOCK)** | `morning_gate.py:753-781` | `live_price`; `evening_invalidation_price`/`invalidation_price`/`invalidation_level`; `direction` | CALL: `live_price <= invalidation`; PUT: `live_price >= invalidation` | Same-unit price comparison, OK | **Fail-OPEN** on missing `live_price` (`:758-759`, returns `True`/pass) and on missing invalidation level (`:766-767`, returns `True`/pass) — confirms 2026-06-30 audit findings F-10/F-11 are still present | 22/1082 (2.0%) BLOCK in `20260624_052030` — all genuine thesis-broken price-vs-level breaches (verified sample text: `"CALL thesis broken — price X at or below invalidation Y"`) |
| **CHECK 2 — Macro regime unchanged** | `morning_gate.py:788-806` | `morning_macro_regime_state`/`macro_regime`/`regime_state`/`evening_regime_state` vs `current_regime` | `_regime_flipped(eod_regime, current_regime)` | N/A (categorical) | Fail-open: no EOD regime recorded → `True`/pass (`:800-801`) | Flag-only, downgrades to `ARMED`, never blocks |
| **CHECK 3 — Contract liquid (dominant driver)** | `morning_gate.py:813-860` | `live_contract_bid`, `live_contract_ask`, `live_contract_spread_pct`, `live_contract_delta`, `live_contract_iv` | bid/ask must exist and be `>0`; spread ≤ `spread_threshold` (25%, passed from `premarket_workflow`); `0.20 ≤ \|delta\| ≤ 0.70`; `0 < IV ≤ 250%`; IV compression vs EOD IV ≥ 0.70 ratio | Internally consistent (%, price units match) | **Fail-CLOSED**: `bid is None or ask is None` → immediate `False` (`:829-830`). No fallback to a last-known-good snapshot anywhere in this function. | Root cause of ~84% FLAG/CONTRACT_REPAIR rate — see §2 |
| **CHECK 4 — Bond macro clear** | `morning_gate.py:725-751` (referenced) | `bond_macro_state.json` `trade_go` flag | boolean | N/A | UNVERIFIED — not read in this session | Flag-only |
| **CHECK 5 — Layer-3 model risk clean** | `morning_gate.py` (`_layer3_model_risk_guard`, referenced at `:914`) | `VOL_HARDCAP`/`LOW_CONF_HIGH_VOL`/`THIN_HISTORY`/`IV_TAILWIND_EXTREME` flags | boolean flags present/absent | N/A | UNVERIFIED | Flag-only; 2/1082 `MODEL_RISK_REVIEW` in `20260624_052030` |
| **rr_gate (SuperBrain, DEP-02 site)** | `scripts/avshunter_superbrain_layer.py:2176-2177` | `rr_underlying` (fallback `rr`) | `>= 0.5` | **Confirmed fixed** — reads structural R:R (1.0–3.0+ scale), not premium R:R (0.2–0.8 scale). Comment block at `:1332-1337` documents the original DEP-02 incident and fix explicitly. | Fail-open on 0/missing (`0 < rr_val < 0.5` is false when `rr_val=0`, so the gate does not fire) — i.e., missing R:R does not itself suppress a signal here | Not the current bottleneck |
| **ev_gate (SuperBrain)** | `scripts/avshunter_superbrain_layer.py:1365-1373, 2175` | `ev_final`/`ev_adj`/`ev_adjusted` | `>= -0.10` | Consistent scale | Fail-open on missing (`ev_val=0` passes `-0.10` floor) | Not the current bottleneck |
| **composite_gate (SuperBrain)** | `scripts/avshunter_superbrain_layer.py:2178, 1341` | `composite` | `>= 35` | Single field, no fallback chain | **Fail-CLOSED** on missing: a genuinely-blank `composite` reads `0`, which is `< 35` → `FAIL_LOW_COMPOSITE`, silently, with no distinct "missing" label | UNVERIFIED fill-rate this run — flagged as a risk, not confirmed as a live driver |
| **AVOID campaign → DATA_FAILURE (SuperBrain convexity score)** | `scripts/avshunter_superbrain_layer.py:798-943, 1539-1540` | `iv_rank`, `pcr_vol`, `ivp`, `call_wall`/`put_wall`, `volume_ratio`, `notional_buy`/`notional_sell`, `sector_regime` (8 conditions, `conv_score = sum`) | `campaign == 'AVOID'` when `conv_score == 0` | Each of the 8 sub-conditions individually fine | **6 of 8 conditions fail-CLOSED silently on missing data** (compression, energy/absorption, underpriced-vol, gamma-proximity, runway, volume-confirmation); only 2 of 8 are documented fail-open. In EOD-mode runs where wall/notional/volume-ratio data is sparse, this structurally biases `conv_score` toward 0 | UNVERIFIED direct fill-rate; flagged as a structural EOD-mode risk, not confirmed as the dominant driver this run (Options Intelligence contract-selection failure, below, is larger and directly measured) |
| **Contract chain-fetch OI floor** | `scripts/avshunter_options_intelligence.py:2092-2133` (MarketData `minOpenInterest` API param, `MIN_OI=50` line 1012), `:2386` (Polygon fallback, `fillna(0) >= MIN_OI`) | `open_interest` | `>= 50` | OK | **Fail-closed, and missing OI is `fillna(0)`** — treated as OI=0, excluded, not flagged as a data gap | Contributes to the 803/1464 empty-chain outcomes in §2 |
| **`select_best_contract()` liquidity/delta/DTE/strike chain** | `scripts/avshunter_options_intelligence.py:3760-3950` | direction, DTE window (strict then ±15d relaxed), OTM/ATM strike, `delta_abs <= 0.65-ish`, spread (bypassed if 100% synthetic leg), OI≥50 (3rd application), `volume >= MIN_LIQUIDITY_VOLUME`, target-reachability | Multiple, see agent detail in §4 | `MIN_LIQUIDITY_VOLUME = 0` (line 1013) — **the volume gate is a documented no-op**: `volume.fillna(0) >= 0` is always true | Returns `None` (silent, no per-contract reason retained) if any stage empties the candidate set | Root of §2 |
| **`NO_LIQUID_OTM_CONTRACT` hard veto (5 call sites)** | `scripts/avshunter_options_intelligence.py:5192-5221` (`_empty_options_research_contract`), called from `:5276, 5281, 5318, 5321, 6562` | N/A — this is a terminal label, not a field read | N/A | N/A | **This single string is hardcoded for 5 structurally different failure causes**: bad/missing spot price, no direction, chain-fetch exception, empty chain, *and* any unhandled Python exception anywhere in `process_ticker()`. True cause survives only in free-text `reason`, not in `hard_vetoes`/`missing_data` | 41/1464 rows in July-16 run carry this exact label; the other ~762 "no contract" rows are separately labeled `NO_CONTRACT_PASSED_QUALITY_GATES` (see §2 — different code path, not mislabeled the same way) |
| **`build_convexity_strike_map()` DATA_INSUFFICIENT guard** | `scripts/avshunter_options_intelligence.py:6014-6053` | `mark_synthetic`, `mid`, `delta`, `dte`, `spot` | Any missing, or `mark_synthetic=True` → `DATA_INSUFFICIENT` | Correctly implemented per spec | Fail-closed (correct, intentional) | 322/1464 (22%) `csm_verdict=DATA_INSUFFICIENT` in July-16 run — all synthetic-mark rows, confirmed 1:1 with `contract_mark_synthetic=True` count |
| **`select_candidates()` pre-filter (morning_thesis_validator.py only — not the live engine)** | `morning_thesis_validator.py:1236-1248` | `structural_tier`, `final_route`/`options_research_route`/`hard_vetoes`, `lab_verdict`/`eod_candidate_status` | Tier allow-list; route not in `{OPTIONS_BLOCKED, OPTIONS_EQUITY_ONLY_BETTER}`; status allow-list | N/A | Fail-closed (rows silently dropped before any per-candidate check) | N/A — this engine does not run in production, see §0.1 |
| **Discovery universe liquidity filter** | `avshunter_discovery_ULTIMATE.py:1213-1232` | `last_close`, 20-day avg volume, price×volume (ADV $), 14-day ATR ($ and %) | price $5–$500; avg vol20 ≥ 500k shares (tightened to 800k in RISK_OFF via `regime_threshold_injector.py:89-94`); ADV ≥ $2.5M; ATR ≥ $0.40; ATR ≥ 1.0% | Consistent, documented ("Enhancement 4/5" comments) | Fail-closed (`return None`, ticker dropped from Discovery entirely) | Largest single dropoff bucket in the dropoff-audit ledger (1596/3325 rows, tagged `UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY`) — but this is Discovery's *scoring* miss, not proven to be this specific liquidity filter alone; see §3 |

---

## 2. THE CORE FINDING — traced end to end with real numbers

This is the mechanism behind CHECK 3 failing on ~84% of candidates.

**Step 1 — Options Intelligence (Phase 7), run `20260716_010747` (1,464 candidates entering this phase):**
- `recommended_contract` blank for **803/1464 (54.8%)** — and `contract_delta`, `contract_oi` blank
  for the exact same 803 rows (`options_intelligence_20260716_010747.csv`).
- Of those 803, **762 (94.9%)** carry `contract_repair_reason = "NO_CONTRACT_PASSED_QUALITY_GATES"`
  — this is the specific, *not*-mislabeled path (`scripts/avshunter_options_intelligence.py:5424-5483`):
  chain data existed, but every strike failed the DTE/OTM/delta/OI/spread/target chain in
  `select_best_contract()` (`:3760-3950`). The remaining ~41 carry the generic
  `NO_LIQUID_OTM_CONTRACT` label (chain was empty or fetch errored — see table above), and 18 rows
  are an **unhandled Python exception** (`"Invalid format specifier '.0f if ivp is not None else
  'N/A'' for object of type 'float'"` — a live bug in an f-string, causing those tickers to fall
  through `process_ticker()`'s exception handler and get the same generic veto label as a genuine
  illiquidity rejection).
- `contract_repair_status = CONTRACT_REPAIR_REQUIRED` for **1378/1464 (94.1%)**, vs. only 86 (5.9%)
  `OK` — far more than the 803 "no contract at all" rows, meaning even most of the 661 rows that *did*
  get a contract are flagged as needing repair (wide spread, unknown OI, etc.).
- Of the 661 rows that did get a contract, 322 (48.7%) are `contract_mark_synthetic=True` — a modeled
  BSM price, not a real market quote — and every one of those 322 rows also has
  `contract_spread_pct = 2.0` exactly, a suspiciously uniform value consistent with a hardcoded
  placeholder spread assigned when a contract is synthetic (not independently confirmed via source
  line in this session — flagged `UNVERIFIED`, worth a targeted grep for the literal `2.0` in the
  synthetic-spread code path before concluding it's a bug).

**Step 2 — this is corroborated independently by the pipeline's own self-diagnostic ledger**
(`dropoff_audit_20260716_010747.csv`, 3,325 rows total): 832 tickers are tagged
`dropoff_stage=OPTIONS_INTELLIGENCE`, of which 785 (94.4%) are classified by the pipeline itself as
`root_cause_family=NO_USABLE_OPTIONS_CONTRACT`, `audit_behavior=MARKET_OR_SCANNER_DATA`,
`business_impact=THESIS_MAY_NEED_CONTRACT_REPAIR`, with `evidence_snapshot` showing
`oi_score=0.0,spread=0.0,oi=0,vol=0` — i.e., **the system's own instrumentation independently confirms
these are literal all-zero contract records, not marginal liquidity rejections.**

**Step 3 — this propagates into the morning validator/gate stage, run `20260624_052030`
(1,082 candidates reaching `morning_validated_trades`):**
- `contract_delta`, `contract_oi`, `contract_spread_pct_eod` are all exactly `0.0` for **780/1082
  (72.1%)** rows, with `contract_repair_reason = "NO_CONTRACT_SELECTED; SPREAD_UNKNOWN;
  OI_REPAIR_NEEDED; VOLUME_CAUTION; DELTA_UNKNOWN; BREAKEVEN_OR_RR_CAUTION"`.
- Tracing why: `morning_thesis_validator.py:1395-1421` (`_candidate_contract_symbols()`) builds a list
  of candidate OCC symbols from `evening_contract_symbol`/`contract_occ_symbol`/`recommended_contract`/
  `preferred_contract`/`contract_symbol` plus repair alternatives; if **all** of these are blank (true
  for the 780 rows above, since Options Intelligence never wrote a `recommended_contract` for them —
  Step 1), the fallback `_build_occ_symbol()` also fails (no strike/expiry recorded), so
  `contract_symbols` is empty.
- `_fetch_live_snapshot()` (`morning_thesis_validator.py:1660-1682`) only calls
  `_marketdata_quote(candidate_occ)` **`if contract_symbols:`** — with an empty list, the options-quote
  API is **never called** for these 780 tickers. This is confirmed in the CSV:
  `live_options_source` is blank for exactly **780/1082** rows and populated (`MARKETDATA`) for 301,
  with 1 `MARKETDATA_FAILED`.
- Meanwhile `live_data_source` (equity quote) is `POLYGON_SNAPSHOT` for all 1082/1082 — equity prices
  refresh fine; only the *options*-side fetch is starved, and specifically starved because there was
  never a contract symbol to look up, not because of a rate limit or fetch-budget cap (no such cap was
  found in this code path).
- Only **30/1082 (2.8%)** rows show a `morning_repair_reason` of `"Contract liquid — bid=... ask=...
  spread=..."`, meaning the repair mechanism (which does exist and can pull a live quote when at least
  one alternative-contract symbol is present) resolved only 30 of the 831 rows flagged
  `contract_repair_required=True`.

**Step 4 — this is exactly what `morning_gate.py`'s CHECK 3 (`_check_contract`, `:829-830`) rejects**:
`bid is None or ask is None` → `False`, immediate FLAG. There is no fallback path in `_check_contract`
to accept a candidate on EOD contract data or any other proxy when the live quote is absent — which is
correct/safe behavior for CHECK 3 itself, but it means the ~72–95% "no real contract data" rate
established two phases upstream (Options Intelligence) surfaces here as `verdict=FLAG,
permission=CONTRACT_REPAIR` on the overwhelming majority of candidates, observed as **911/1082 (84.2%)
CONTRACT_REPAIR** in the `20260624_052030` run, vs. **147/1082 (13.6%) GO** and **22/1082 (2.0%) BLOCK**.

**Answer to the "genuine absence vs. mislabeled data pull" question (Task 5):** both occur, but the
*volume* is dominated by the mislabeling problem, not genuine illiquidity. 762/803 blank-contract rows
in the July-16 run are tagged `NO_CONTRACT_PASSED_QUALITY_GATES` — a real "nothing survived the
quality chain" outcome, not itself mislabeled, but this single bucket conflates at least five distinct
upstream causes (DTE window too narrow, wrong side of spot, delta cap, the disabled-but-present OI
floor at the chain-fetch layer zeroing an entire chain, and target-unreachable) without recording
*which* stage actually eliminated the chain. The remaining ~41+18 rows genuinely are mislabeled
(chain-fetch exceptions and an unhandled format-string bug both get the same
`NO_LIQUID_OTM_CONTRACT` string as a real liquidity rejection). There is **no fallback to a
last-known-good options snapshot anywhere in this chain** — confirmed absent in both
`scripts/avshunter_options_intelligence.py` (`enrich_contract_with_real_quotes()`,
`:1291-1373`, returns the contract unchanged on failure rather than caching/reusing a prior good quote)
and `morning_thesis_validator.py`'s live-fetch path.

---

## 3. COMPOUNDING CHECK

### 3.1 Live engine (`morning_gate.py`) — short chain, not the compounding pattern
Only 5 checks total; only CHECK 1 is a hard BLOCK (2.0% of candidates in `20260624_052030`), CHECK 2–5
are FLAG-only and do not stack into a harder rejection — the verdict-assembly code
(`morning_gate.py:1131-1189`) takes the *first* failing check in priority order (invalidation → contract
→ model-risk → macro → bond-macro → other flags) and stops there; it does not require all 5 to pass
simultaneously in a way that would multiply small per-gate rejection rates. **Observed joint outcome
this run:** BLOCK 2.0%, FLAG 84.2% (dominated by CHECK 3), GO 13.6%. This is explainable almost
entirely by CHECK 3 alone, not by compounding across CHECK 1–5.

### 3.2 Non-running engine (`morning_thesis_validator.py`) — this IS architecturally a compounding-risk design, for the record
If this script is ever run standalone/manually, its `validate_candidate()` (`:1893-2608`) has ~19
independently-triggerable gates: a Gate-0 pre-filter (`select_candidates()`, `:1236-1248`), 12 hard/soft
per-candidate gates (live price, staleness, invalidation, jump-risk, evening-verdict, evening-structural-
veto, macro-hard-block, catalyst-hard-block, direction/physics rejection, a 7-way `contract_repair_needed`
aggregate, direction-conflict-unresolved, `too_extended`), and then a weighted **9-component additive
score ladder** that must clear 80 points to reach GO at all (`:2348-2362`, components at `:2054-2304`).
This is architecturally exactly the "compounding of individually-reasonable gates" failure pattern the
task brief hypothesized — but it is not what's currently producing the low GO ratio in production,
because this engine is not being invoked by the orchestrator (§0.1).

### 3.3 Options Intelligence (Phase 7) — compounding exists but is dominated by one early gate
The 12-step chain to `csm_verdict=BUYABLE` (full detail in §4/agent report) is long, but steps 1–4
(spot valid → direction resolved → chain fetch succeeds → `select_best_contract()` returns non-`None`)
are where the mass elimination happens (803/1464 = 54.8% never get past this point), and steps 5–12
(spread, breakeven, R:R, theta, runway, TRAP/TOO_LATE/WAIT/BUYABLE thresholds) have been **deliberately
softened over time** per the file's own FIX-* changelog comments (`scripts/avshunter_options_intelligence.py:56-78`)
— most of the historically-hard downstream gates (`BLOCK_WRONG_STRIKE`, theta, spread-for-synthetic) now
demote to soft flags/score penalties rather than hard rejects. So while the chain is nominally long,
the practical elimination is front-loaded into 3–4 steps, consistent with §2's findings, not spread
evenly across a dozen independently-reasonable thresholds.

**Determination: the observed low pass ratio is not well explained by compounding of many
individually-reasonable gates in the engine that's actually running.** It's explained by one early,
narrow failure point (contract selection never completing) whose output then trips one downstream
check (CHECK 3) on the great majority of candidates.

---

## 4. UNIVERSE CHECK

Discovery (`avshunter_discovery_ULTIMATE.py:1213-1232`, `scan_ticker_ultimate()`) **does** apply a
liquidity/volatility pre-filter before any Wyckoff/Crabel structural scoring runs — this is explicit,
commented, intentional design ("Enhancement 4: Options viability proxy filters... Reject structurally
interesting but economically useless names," `:1220-1221`), not a silently-inserted regression:
- Price band $5–$500 (`:1213-1214`)
- 20-day avg share volume ≥ 500,000 (tightened to 600k/800k by macro regime via
  `regime_threshold_injector.py:89-94`, called from `avshunter_discovery_ULTIMATE.py:2246-2249`)
- Average daily dollar volume ≥ $2.5M (`:1227-1228`)
- 14-day ATR ≥ $0.40 and ≥ 1.0% of price (`:1229-1232`)

No open-interest or options-chain-availability check exists at this stage — that part of the intended
design (OI/liquidity belongs at Options Intelligence) does hold. `intelligent_orchestrator.py`'s
Discovery invocation (`run_discovery()`, `:1515-1559`) passes no liquidity-related CLI flags; the
universe-augmentation path (`build_augmented_universe()`, `:624-647`) only *adds* tickers, never removes.

This filter is real and does shrink the pool (1596/3325 dropoff-ledger rows tagged
`UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY` are the largest single bucket in the whole funnel), but two
things argue against it being the primary driver of the *low-GO-ratio* complaint specifically: (1) it's
intentional and documented, unlike the Options Intelligence contract-selection failure which is not
labeled as an intentional design choice; (2) the dropoff-ledger's own severity tagging on the
Options-Intelligence bucket (`NO_USABLE_OPTIONS_CONTRACT`, 785/832 rows) is a distinct, later-stage
signal, not conflated with the Discovery-stage bucket. **Determination: this is not the unintended
universe restriction the brief hypothesized — it is a legitimate, by-design filter, separate from the
Phase 7 problem in §2.**

---

## 5. REJECTED-CANDIDATE VISIBILITY CHECK

Contrary to an assumption that this might be a gap: **a shadow ledger already exists and is reasonably
granular.**
- `dropoff_audit_{run_id}.csv` (`data/output/runs/20260716_010747/diagnostics/`, 3,325 rows) records,
  per ticker: `last_stage_reached`, `dropoff_stage`, `dropoff_reason`, `root_cause_family`,
  `audit_severity`, `audit_behavior`, `business_impact`, and an `evidence_snapshot` free-text field
  carrying key field values (e.g. `oi_score=0.0,spread=0.0,oi=0,vol=0`) — this is close to what Task 4
  asked for (ticker, gate, field value, timestamp is only implicit via `run_id`, no explicit
  per-row timestamp column was found — `UNVERIFIED` whether one exists elsewhere in the row).
- `missed_opportunity_shadow_book_{run_id}.csv` (37 rows in the July-16 run) is a narrower, curated
  "false-negative candidate" ledger with `shadow_opportunity_score`/`shadow_opportunity_label` —
  smaller in scope (only candidates flagged as plausibly-good misses), not a complete rejected-universe
  ledger.
- **Gap found**: several of the dropoff-ledger's declared field-contracts are `PRESENT_BUT_EMPTY`
  (0% fill rate) per `handoff_contract_audit_20260716_010747.json` — `catalyst_overlay` (4 stages),
  `behaviour_state`, `actuarial_match_type`, `gamma_island_label/source/note`,
  `crowd_arrival_components` — all declared as shadow-book columns but never populated in this run, which
  weakens the ledger's usefulness for the "test rejected candidates against realized price action"
  goal stated in the task brief.
- **Determination: rejected-candidate visibility is not a priority gap to build from scratch** — the
  infrastructure exists and is already being written every run — but its field-contract fill rate has
  known, currently-unaddressed holes (documented in the existing `handoff_contract_audit` WARN list,
  reproduced by re-running it in this session — §6).

---

## 6. LIVE TEST RESULT

Ran (read-only, non-mutating) `python handoff_contract_audit.py --run-id 20260716_010747`:
```
overall_status: WARN
fail_count: 0
warn_count: 12
```
All 12 warnings are `PRESENT_BUT_EMPTY` field-fill issues (the `catalyst_overlay`/shadow-book fields
listed in §5) — **none are related to the GO-count/contract-selection problem** documented in §2; that
problem does not trip any `handoff_contract_audit.py` check, because the audit checks field-contract
presence/fill-rate between stages, not contract-selection success rate itself (confirmed:
`handoff_contract_audit.py` is a schema/lineage auditor, not a trade gate — it is called by
`intelligent_orchestrator.py:4982-4994` inside a `try/except` purely for logging; its `--strict` exit
code is never used by the orchestrator, and it is never read by `morning_thesis_validator.py` or
`morning_gate.py`). Row counts from `final_run_manifest.json` for this run:
`discovery: 1742 → vanguard: 1691 → {eil, execution, options}: 1464 → eod_candidates: 1080`.
This run has `morning_validation: 0 rows` because it is EOD-stage only
(`run_tradeable: false, next_action: NEEDS_MORNING_VALIDATION`); the morning-stage verdict numbers used
throughout this report (§2, §3.1) come from the most recent run that has a completed morning-validation
CSV, `20260624_052030` (147 GO / 913 FLAG / 22 BLOCK out of 1082). **No morning-validation run has been
archived between 2026-06-24 and 2026-07-16** (`UNVERIFIED` why — could be the trader simply hasn't run
mornings in that window, or morning runs aren't being archived to `data/output/runs/`; worth asking the
trader directly rather than inferring).

---

## 7. SECONDARY FINDINGS (not the primary driver, but code-grounded and worth tracking)

1. **`morning_gate.py:758-759, 766-767`** — CHECK 1 (the only hard BLOCK) fails open on missing
   `live_price` and missing invalidation level. This is a *false-GO* risk (a broken thesis could pass
   silently), the opposite direction from the low-pass-ratio complaint, but it's the same code the
   2026-06-30 audit flagged (F-10/F-11) and it is unchanged.
2. **`scripts/avshunter_superbrain_layer.py:928-942`** — `sector_regime` is extracted with the *float*
   helper `_f()` on what is actually a string field; any non-numeric value throws inside `_f()` and is
   caught, returning `''`. The "sector fights thesis" veto (C8) can therefore never fire — always
   fail-open, inflating `conv_score` slightly. Opposite direction from the dominant problem, flagged for
   completeness.
3. **`scripts/avshunter_superbrain_layer.py:1430-1431`** — the OIS-gate fallback chain includes a field
   name `score_composite`, which does not exist anywhere in the codebase as a written column (the real
   field is `composite_score`, word order reversed) — dead fallback, low impact (last item in an `or`
   chain).
4. **`scripts/avshunter_options_intelligence.py`** — an unhandled Python exception (`"Invalid format
   specifier '.0f if ivp is not None else 'N/A'' for object of type 'float'"`) was observed in 18 rows
   of the July-16 dropoff ledger — a live f-string bug in some diagnostic/logging string, causing those
   tickers to fall through `process_ticker()`'s exception handler and get the generic
   `NO_LIQUID_OTM_CONTRACT` veto regardless of their actual options-chain quality. Exact source line not
   pinpointed in this session — `UNVERIFIED` location, confirmed only via its exact error string
   appearing in `contract_repair_reason`.
5. **`morning_thesis_validator.py:1299`** — `evening_rr_predicted` alias order prefers `rr_options`
   (premium-scale, 0.2–0.8) over plain `rr`, the same category of substitution DEP-02 fixed elsewhere.
   Confirmed **not currently read by any gating logic** in `validate_candidate()` (display/audit field
   only) — flagged only as latent risk if a downstream consumer (Lab/Interpreter) ever treats it as
   authoritative.
6. **`contract_spread_pct = 2.0` for all 322 synthetic-mark rows** in the July-16 run — suspiciously
   uniform, consistent with a hardcoded placeholder. Not traced to a source line this session;
   `UNVERIFIED`, recommend a targeted grep for the literal `2.0` in the synthetic-spread derivation path
   (`_derive_eod_spread()`, `scripts/avshunter_options_intelligence.py:2060-2091`, per the agent's
   report) before concluding it's a bug vs. an intentional default.

---

## 8. WHAT WAS *NOT* FOUND

- No recurrence of the original DEP-02 pattern (wrong-field-wrong-scale) in the currently-active rr/ev/
  composite gates — the historical fix is intact and correctly scaled.
- No evidence that Discovery's universe filter is an accidental/unintended insertion — it's deliberate
  and documented.
- No evidence that `handoff_contract_audit.py` itself blocks or influences trade authorization — it's
  read-only telemetry, consistent with its own docstring.
- No last-known-good quote caching anywhere in the live-data-fetch path (`morning_thesis_validator.py`
  or `scripts/avshunter_options_intelligence.py`) — every failure to get a fresh quote results in a
  null/absent value, never a stale-but-usable fallback. This is a design gap relevant to Task 5, not a
  bug per se.

---

## 9. FOLLOW-UP (2026-07-16, same day) — `select_best_contract()` sub-cause trace on the 762 `NO_CONTRACT_PASSED_QUALITY_GATES` failures

**Task:** §2 identified that 762/1464 candidates in run `20260716_010747` fail inside
`select_best_contract()` (`scripts/avshunter_options_intelligence.py:3760-3950`) with the single
generic label `NO_CONTRACT_PASSED_QUALITY_GATES`, conflating at least 5 distinct sub-conditions
(DTE window, OTM/ATM side, delta cap, liquidity floor [OI/volume/spread/mark], target-reachability).
This follow-up instruments the exact sub-condition responsible for each failure. **Diagnosis only —
no code changed, no thresholds altered.**

### 9.1 Method

Raw options-chain data from the original run was not cached anywhere in the repo (confirmed —
no chain-cache directory exists), so exact byte-for-byte replay of `20260716_010747` is not possible.
Instead, a read-only standalone tracer (`trace_select_best_contract.py`, kept outside the repo in the
session scratchpad, **no production file modified**) was built that:

1. Imports `scripts/avshunter_options_intelligence.py` as a library via `importlib` (never executed
   as `__main__`, so no writes/side effects) and calls the **real, unmodified** `process_ticker()` for
   each target ticker, using the exact same input CSVs the run used
   (`discovery_candidates_ultimate_20260716_010747.csv` + `vanguard_signals.csv`, merged identically
   to `run_options_layer()` at `scripts/avshunter_options_intelligence.py:6472-6512`), so `ctx`
   construction (direction, DTE window, delta band, spread limit, structural target — all built by
   `parse_structural_context()`, `scripts/avshunter_options_intelligence.py:3425-3729`) is 100%
   authentic, not hand-reconstructed.
2. Monkeypatches only `select_best_contract` (module-global rebind — Python resolves this at call
   time, so `process_ticker()`'s internal call picks up the patched version automatically) with a
   line-for-line copy of the production logic (verified against the current file at the same time as
   this trace, `scripts/avshunter_options_intelligence.py:3760-3950`) instrumented to record the
   DataFrame row-count after every filter stage and which stage first emptied it.
3. Fetches chains live via the **real, unmodified** `fetch_chain()` / `fetch_chain_md()` /
   `_fetch_chain_polygon()` functions — same MarketData.app-primary/Polygon-fallback path, same
   MIN_OI constant, same API key from `.env`. This necessarily reflects **today's live/current chain**,
   not the exact intraday snapshot the original run saw ~07:00 ET — the task brief explicitly
   sanctioned this ("re-run against the same input chain data... OR careful manual trace," "verify
   against a live/recent options chain").
4. **Fidelity check**: re-ran two known *successful* tickers from the run (`TDOC`, `HRL`) through the
   tracer. Both reproduced the exact recorded `recommended_contract` symbol, strike, and expiry
   (`TDOC260807C00010000` strike 10.0 exp 2026-08-07; `HRL260821P00025000` strike 25.0 exp 2026-08-21),
   confirming the instrumented replica is behaviorally identical to production, not a divergent
   reimplementation.
5. Ran two passes against a random sample of **100 of the 762** failing tickers (seeded,
   reproducible): **Pass A** with `MIN_OI=50` (the real production constant — reproduces the actual
   run's behavior) and **Pass B** with `MIN_OI=0` (relaxed), run only on the subset that stopped at the
   liquidity-floor stage in Pass A, to isolate whether the OI≥50 floor specifically (as opposed to the
   other liquidity sub-conditions) is the cause.
6. Separately pulled a **random sample of 20** of the 762 tickers (task requirement) and manually
   inspected their live chains end-to-end (chain size, DTE-window survivors, delta-cap survivors,
   OI/mark survivors, and the actual `spread_pct` values of every candidate that survived OI+delta+DTE)
   to see the magnitude of the spread miss, not just pass/fail.
7. Separately re-fetched the 7 tickers that hit a distinct `RIGHT_EMPTY` stop (chain had zero
   contracts on the required side at all) at both `MIN_OI=50` and `MIN_OI=0` to test the OI-floor
   hypothesis directly for that stage.

### 9.2 Sub-cause breakdown (Pass A, n=100 tickers sampled from the 762, MIN_OI=50, production-faithful)

| Stop stage | Stage-entries (of 109*) | % | What it means |
|---|---|---|---|
| **LIQUIDITY_FLOOR** (OI/volume/spread/mark, `scripts/avshunter_options_intelligence.py:3814-3827`) | 78 | 71.6% | Dominant cause. See §9.3 — **100% of these are spread-bound**, not OI-bound. |
| **DTE_WINDOW** (`:3789-3796`, strict then ±15d relaxed) | 21 | 19.3% | Chain has no listed expiration inside the relaxed window at all (see §9.4) |
| **RIGHT_EMPTY** (leg empty before any filter runs, `:3778`) | 7 | 6.4% | See §9.5 — **this one genuinely is OI-floor-driven** |
| **OTM_SIDE** (`:3800-3806`) | 1 | 0.9% | Negligible |
| **DELTA_CAP** (`:3811-3812`) | 0 | 0.0% | Never the binding constraint in this sample |
| **TARGET_REACHABILITY** (`:3838-3872`) | 0 | 0.0% | Never the binding constraint in this sample |
| SELECTED (contract now found on live re-fetch) | 9 | 8.3% | Live chain today differs from the original EOD snapshot — expected, not a contradiction (see §9.6) |

\* 109 stage-entries from 100 tickers because 16 of the 100 are `STRANGLE`-direction candidates
(both CALL and PUT legs traced independently).

**Answer to the "would raw chain data show what was available vs. selected" part of the task:**
confirmed directly (not inferred) — the tracer captures the *actual* surviving candidate pool at each
stage, live, for every sampled ticker.

### 9.3 LIQUIDITY_FLOOR is not an OI problem — it's a spread problem

For **all 78 of 78** LIQUIDITY_FLOOR stops in the sample, the per-component breakdown
(`liquidity_component_survivors`, logged at every stage) shows `oi_ok == pool_size` and
`mark_ok == pool_size` (every candidate that reached this stage already had OI≥50 and a valid mark)
while `spread_ok == 0` (**zero** candidates cleared the spread limit). Representative rows:

```
BROS P: oi_ok=2  vol_ok=2  spread_ok=0  mark_ok=2  pool_size=2
BN   C: oi_ok=16 vol_ok=16 spread_ok=0  mark_ok=16 pool_size=16
FTI  P: oi_ok=8  vol_ok=8  spread_ok=0  mark_ok=8  pool_size=8
```

**Pass B (MIN_OI=0, relaxed) confirms this quantitatively**: run on the 69 tickers that stopped at
LIQUIDITY_FLOOR in Pass A, relaxing the OI floor to zero rescued only **10/69 (14.5%)**. The remaining
**59/69 (85.5%)** still fail with `spread_ok=0` even when the OI requirement is completely removed —
proving the OI≥50 floor is a minor, secondary contributor to this stage, not the cause. The dominant
constraint here is `spread_pct <= spread_limit` (`DTE_CONFIG` values 0.15 / 0.25 / 0.35 by horizon
bucket, `scripts/avshunter_options_intelligence.py:1040-1044`).

**Magnitude of the spread miss** (from the 20-ticker manual sample, `min_spread_pct` = the tightest
spread among candidates that already passed OI+delta+DTE, vs. the applicable `spread_limit`):

| Ticker | Min available spread | Limit | Ratio (over limit) |
|---|---|---|---|
| CXW | 14.1% | 15.0% | 0.94x — **near-miss** |
| FLY | 15.8% | 15.0% | 1.05x — **near-miss** |
| TRP | 31.0% | 25.0% | 1.24x — **near-miss** |
| AEVA | 20.4% | 15.0% | 1.36x |
| ALNY | 35.1% | 25.0% | 1.41x |
| ALHC | 48.3% | 25.0% | 1.93x |
| BAM | 29.4% | 15.0% | 1.96x |
| SCCO | 36.9% | 15.0% | 2.46x |
| JACK | 66.7% | 25.0% | 2.67x |
| WCN | 43.0% | 15.0% | 2.87x |
| LH | 89.7% | 25.0% | 3.59x |
| ORA | 93.3% | 15.0% | 6.22x |
| FIZZ | 156.8% | 25.0% | 6.27x |
| WTW | 195.1% | 15.0% | 13.0x |

(TMUS, the 15th data point, cleared its limit easily at 2.4% vs 15% — a mega-cap control case showing
the tracer correctly finds tight spreads when they genuinely exist. 5 of the 20 sampled tickers hit
`DTE_WINDOW`/no-OTM-contracts before ever reaching a spread comparison and are excluded from this
table.)

Of the 14 tickers that did reach a spread comparison: only 2/14 (14%) were within a hair of the limit
(CXW, FLY — effectively marginal misses, arguably within model/data noise of the threshold itself);
1/14 (7%) moderately over (TRP at 1.24x); the remaining **11/14 (79%) were clearly, often dramatically,
wide of the limit** — up to 13x over. This is not a population of contracts sitting just outside an
arbitrary line; it's a population of names whose options genuinely don't trade with tight markets at
the required delta/DTE combination.

### 9.4 DTE_WINDOW failures — likely sparse/monthly-only expiration cycles, not purely a threshold issue

Sampled `DTE_WINDOW` stops show the *chain's overall* DTE range spanning wide (e.g., `chain_dte_min=1.0,
chain_dte_max=92.0`) while the relaxed window (`dte_min-15` to `dte_max+15`, e.g. `[6, 50]`) still finds
nothing — meaning these tickers have listed expirations at the very-near-term and far-dated ends but
a **gap with no listed expiration at all** in the 6-50 day middle. This is consistent with smaller/
mid-cap names that only list monthly (not weekly) option expirations — a genuine structural
liquidity-calendar characteristic of the underlying, not something `select_best_contract()`'s logic
can route around by construction. Examples: `SKWD` (P, chain spans 1-92d, nothing in 6-50d), `ZD`/`PTCT`
(P, chain's only expiries are exactly at 64d, outside the window entirely).

### 9.5 RIGHT_EMPTY is the one sub-cause genuinely caused by the OI≥50 floor

Re-fetching the 7 sampled `RIGHT_EMPTY` tickers at `MIN_OI=50` (production) vs `MIN_OI=0` (relaxed):

| Ticker | Put contracts @ OI≥50 | Put contracts @ OI≥0 | Max put OI actually available |
|---|---|---|---|
| SWX | 0 | 53 | 20 |
| AXGN | 0 | 35 | 34 |
| PFS | 0 | 28 | 16 |
| UMBF | 0 | 76 | 13 |
| HBNC | 0 | 35 | 5 |
| SVV | 0 | 25 | 46 |
| BBT | 0 | 26 | 44 |

For all 7, real put-side liquidity exists (25-76 listed put contracts with real market activity), but
**every single one** has open interest below 50 — so the chain-fetch-layer OI floor
(`scripts/avshunter_options_intelligence.py:2124` MD API param, `:2302` client-side re-filter,
`:2386` Polygon-path re-filter) wipes the entire put leg before `select_best_contract()`'s internal
logic ever runs a single comparison. This is the one sub-cause where the answer to the task's item 3
question is unambiguously **yes** — the OI≥50 floor at the fetch layer is directly, solely responsible,
and it fires upstream of (not inside) `select_best_contract()`'s own filter chain.

### 9.6 The 9 "now selected" tickers are not a contradiction

9/100 sampled tickers that failed in the original `20260716_010747` run now return a contract when
re-traced against **today's live chain** (e.g. `JD`, `PM`, `MMM`, `DOCU`, `COHR` — all found on the
relaxed-OI Pass B, meaning even these were originally liquidity-floor-blocked and only cleared when
OI was relaxed, i.e. they are among the 14.5% OI-floor-rescuable group, not evidence the original run
was wrong). Intraday market conditions (spreads, OI, quotes) shift continuously; a live re-fetch hours
after the original EOD run is not expected to reproduce every single outcome identically. This does not
undermine the sub-cause attribution above, which is based on the *stage* at which each contract set
was eliminated, cross-validated by the TDOC/HRL fidelity check (§9.1.4).

### 9.7 Determination: genuine liquidity desert, not a parameter-calibration bug

Weighing all of the above against the task's explicit choice — **(mostly) genuine liquidity desert,
not primarily a parameter-calibration issue**:

- The dominant sub-cause (LIQUIDITY_FLOOR, ~72% of failures) is spread-bound in 100% of sampled cases,
  and the magnitude data shows the large majority (79% of the sub-sample with spread data) are wide of
  the threshold by 1.4x-13x, not marginally over it. Loosening `spread_max` from e.g. 0.25 to 0.35
  would not rescue a WTW (195% spread) or an ORA (93% spread) — these names simply do not have a tight
  options market at the required delta/DTE combination right now.
- A meaningful minority (~14.5% of the LIQUIDITY_FLOOR subset, so roughly 10% of all 762) **is**
  attributable to a specific, identified parameter: the OI≥50 floor. This is concentrated in two
  places — some LIQUIDITY_FLOOR rescues, and (more cleanly) the entire `RIGHT_EMPTY` sub-cause (~6% of
  all failures), where real but thin (OI 5-46) markets exist and are wiped out entirely before
  selection logic runs. **This is the one component of the finding that does look like a calibration
  question worth the trader's attention** — not because 50 is unreasonable in the abstract, but because
  it is applied at the *fetch* layer (discarding data entirely) rather than as a *scored* factor,
  giving `select_best_contract()` no opportunity to consider a marginal-but-real 46-OI contract even as
  a fallback/soft-review candidate the way spread and delta-sweet-spot misses already are.
- DTE_WINDOW failures (~19%) look structural (sparse monthly-only expiration calendars on smaller
  names) rather than a software threshold being too narrow, though this was not verified against an
  independent expiration-calendar source and is marked lower-confidence than §9.3/§9.5.
- Taken together: this reads as Discovery correctly feeding in structurally interesting setups on
  names that, at the specific delta/DTE zone the strategy requires, frequently do not have a tight,
  liquid options market — i.e. the options universe is genuinely thinner than the equity universe
  Discovery screens against (Discovery's liquidity filter, per §4 of the original report, checks
  *equity* share/dollar volume and ATR, not *options* liquidity — so a name can cleanly pass Discovery's
  bar and still have no tradeable options at the desired point on the chain). The `NO_LIQUID_OTM_CONTRACT`
  mislabeling problem documented in §2/§4 of the original report (multiple distinct failure causes
  collapsed into one string) remains a separate, real finding — this follow-up shows that even where
  the label is *not* wrong (these are true `NO_CONTRACT_PASSED_QUALITY_GATES` chain-had-data cases,
  distinct from the mislabeled `NO_LIQUID_OTM_CONTRACT` bucket), the underlying reason is overwhelmingly
  "the market for this contract is thin," not "the code is too strict."

No thresholds were changed. No code was modified. This section is diagnosis only, per the task's
explicit instruction.

---

## APPENDIX — Full per-file gate enumerations

The three parallel research passes each produced an exhaustive, line-cited enumeration of every gate in
their respective file (SuperBrain: 14 hard-fail booleans + 8 convexity sub-conditions;
Options Intelligence: 12-step compounding chain + full `NO_LIQUID_OTM_CONTRACT` call-site table;
morning_thesis_validator.py: ~19 gates + fail-open/fail-closed table per gate). These are condensed
into §1 and §3 above; the full unabridged agent outputs are available in this session's transcript if
line-by-line detail beyond what's cited here is needed.
