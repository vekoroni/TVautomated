# G5 + G9 — one pricer, one pricing basis, both lanes: root cause and design

## Status (ACK, 17 Oct 2026): cut to the minimal version; D1–D3 approved

ACK approved D1 (Lane B shares the pricing module), D2 (IV re-implied from the mid) and D3 (EV3 stays frozen). ACK's instructions:

> "I don't want to keep on changing major things if we do not need to."

> "Ensure both Lane A and B remain giving us the business outcome required."

> "We will implement the rest of the fixes next Saturday."

**BUILT 17 Oct, not committed; receipt: `G5_MINIMAL_BUILD_RECEIPT_20261017.md`.** The build also needed the module to own its American tree (`american_crr_value` / `american_crr_values`, equal to EV3's to 1e-9; EV3 is left frozen), because EV3's tree was too slow for Lane B (689 s). With it, Lane B runs in 393 s against 178 s before.

**Built now (minimal version), 17–18 Oct weekend window:**
- **Item 1: Lane B prices American with dividends.** Lane B's decision-facing values (its shortlist's half-target, level and invalidation values, and the pay flags) use the pipeline's existing pricing function, `domain/option_valuation.option_value`. That is the American tree, with the tastytrade dividend and the run's live rate. Lane B's own contract-selection rules, the $5 cap and its output files are unchanged.
- **Item 2: the card engine uses the live rate.** The callers pass the run's observed rate (`load_market_rate`, with source and date) instead of the 8 Oct fallback.
- **Item 4: daily bid capture.** After the close, a local script (no Claude credits) records bid, ask, mid and quote time for every carded and held contract. That starts the record against which predicted option prices are checked [W16-10, A16-03].
- **Guard test.** It fails if a new option pricer appears outside `domain/option_valuation.py` and the listed existing ones.

**Approved but scheduled for Saturday 24 Oct (the "rest"):**
- D2 implementation (IV re-implied from the mid, with the shared solver);
- moving the remaining eight Lane A engines onto the one module (M3–M9 below);
- the European/American switch for bulk paths;
- DOI's dividend label fix.

These carry the smaller measured effect (§2). Then come G2 (spread model), G1/G7 and G3, each only if the captured bids show the need.

**Business outcome check for both lanes after the minimal build:**
- **Lane A:** the card and Lab book are produced as before. The only change is the rate input (+0.06 points), so the card's return and rank move by less than 0.1 percentage points.
- **Lane B:** the hand-off, shortlist and `best_contract_checked` are produced as before, with American-with-dividend values. The expected change is the measured 17 of 872 pay flips, and a new before/after column shows each one.

The full design follows as written for approval.

---

17 Oct 2026. **For ACK's approval. No code changed.** Filed as fix candidates in
`data\scratch\workaround\lessons\fix_inbox\2026-10-17_options_valuation.md` (G5, G9, G6).
Evidence script: `g5_basis_measure.py` (rows in `g5_basis_measure_20261017.csv`).

Both lanes are covered:
- **Lane A** is the evening and morning pipeline: Options Intelligence → card → Lab → Morning Gate.
- **Lane B** is the split lane: `avshunter_options_standalone.py` → hand-off → triage → deep dives.

Discovery and Vanguard stay frozen.

## 1. What is wrong

**G9: eleven separate option pricers.**
- Seven copies of Black-Scholes, three IV solvers, and two American trees with different step rules.
- Lane B's `avshunter_options_standalone.py` adds the eleventh: European Black-Scholes, no dividends, rate 0.042, vendor IV.
- The same contract therefore gets different values on the card, in the Lab `doi_*` fields, in C12 scoring and in Lane B.
- The "one engine" test (`tests/test_ot4_one_valuation_engine.py`) checks only the card's display.

**G5: no single source for rate, dividend or IV basis.**
- The card engine always uses the 8 Oct fallback rate of 0.0422 on all 2,153 cards on 15 Oct, because its callers never pass a rate (`eod_candidate_engine.py:2887`, `morning_gate.py:1258`). Yet each run's own `macro_snapshot.json` holds the live 3-month T-bill (0.0425 on 13 Oct, 0.0428 on 15 Oct), and DOI already reads it with `load_market_rate`.
- DOI takes its dividend from `ev3_dividend_yield_used`. That field is EV3's default of 0.0 on all 85 rows that carry it, yet DOI marks the dividend as "available", so an assumed zero is labelled as measured. This breaks rule R6.
- Lane B assumes no dividends. 444 of its 874 shortlisted contracts (16 Oct) are on dividend payers.
- Every engine except the empirical shadow feeds the vendor's IV into its own model. The vendor IV was computed with the vendor's own rate and dividend, so our model then fails to reproduce the quoted price.

## 2. Measured against reality (15 Oct Lab cards; 16 Oct Lane B shortlist)

The "one basis" here means: IV re-implied from the quoted mid with the American tree, the run's live rate and the tastytrade dividend. The same scenario is then re-valued with it. The reproduction is exact: my current-basis return matches the card's own figure on 1,127 of 1,127 valued cards, and Lane B's tool on 96% of 874 contracts.

| | Lane A (card engine) | Lane B (standalone tool) |
|---|---|---|
| Entry: current model value against the mid, p10 / p50 / p90 | −0.9% / +0.3% / +1.3% | −4.9% / −0.3% / +4.3% |
| Contracts more than 5% / 10% off the mid at entry | 7% / 3% | **18% / 8%** |
| Re-implied IV minus vendor IV, p10 / p90 (vol points) | −1.5 / +0.5 | −1.1 / +1.2 |
| Target return change, p10 / p50 / p90 (% points) | −0.4 / 0.0 / 0.0 | −2.4 / +0.2 / +2.6 |
| Target return moving more than 10 points | 1% | 4% |
| "Pays" (return ≥ 0) decisions that flip | 9 of 2,100 | 17 of 872 |
| "+20% minimum" decisions that flip | 8 of 2,100 | 13 of 872 |
| Top-50 card rank unchanged | 49 of 50 | — |

**Reading:**
- **On its own, G5 changes Lane A very little.** The card engine is already American with dividends, and the rate gap is 0.06 percentage points.
- **Lane B is affected more.** Its European, no-dividend pricing is visibly off the market on about 1 in 5 shortlisted contracts, and it flips about 2% of its pay decisions.
- **G9's main value is not today's numbers.** It is building G1 (IV at exit), G2 (spreads) and G3 (paths) once for both lanes instead of eleven times.

## 3. Root cause

1. **No owner for pricing.** Each stage was built with its own pricer. The 16 Sep design named one valuation core (C8), but the 17 Sep rule (enhance in place, no new owner) left it with no owner, so it was never built. On 10 Oct, OT4 unified only the card. Lane B was built on 11 Oct as a deliberately self-contained research tool and copied Black-Scholes again.
2. **No owner for the basis.** A live-rate loader exists (`canonical_data/market_rate_observation.py`) and a dividend source exists (`canonical_data/dividend_history.dividend_inputs`), but nothing requires a pricer to use them. Each engine falls back to its own constant.
3. **Vendor IV is treated as model-free.** It is quoted on the vendor's basis, so pricing it on ours misprices the entry. Only the empirical shadow engine re-implies IV (`empirical_option_ev.py:478-501`), and it uses its own copy of Black-Scholes.
4. **The guard test checks display, not code.** Nothing fails when a new pricer appears.

## 4. Design

### 4.1 One pricing module, inside the existing owner (search before building)

`domain/option_valuation.py` already owns the card engine. It becomes the only pricing module. It gains the following functions:

| Function | Purpose |
|---|---|
| `price(side, spot, strike, years, vol, *, rate, dividend_yield, style="AUTO")` | Uses European BSM with a dividend yield unless American exercise is material, and then the American tree. Materiality reuses the existing rule `assess_american_exercise_materiality` (moved here from `deterministic_option_valuation.py`). Index roots stay European, as configured. Returns the value and the model name. |
| `price_vec(...)` | A vectorised version for bulk use (Lane B's 45,000-row thesis table, Phantom, GEX). Uses the tree only on rows where exercise is material. |
| `implied_vol(price, ..., style)` / `implied_vol_vec(...)` | One solver, bounded 0.01–6.0, returning a state: `OK`, `BELOW_INTRINSIC`, `ABOVE_BOUND` or `NO_CONVERGENCE`. |
| `greeks(...)` / `greeks_vec(...)` | BSM Greeks with a dividend yield. Used only where no provider Greek exists (Phantom backfill, GEX). Provider Greeks are still the published Greeks (G4). |
| `pricing_basis(run_dir or as_of, ticker, spot)` | The single source for rate and dividend (§4.2). |

The American tree is copied into this module from `vanguard/ev_engine_v3.py`. EV3 itself is not edited, because Vanguard stays frozen as the control (decision D3).

### 4.2 One pricing basis (configuration in `governed_constants`, `option_valuation_v2`)

- **Rate:**
  1. the run's own `macro_snapshot.json` (`load_market_rate`, PASS);
  2. else the newest run's snapshot within 5 sessions, labelled `STALE_<n>d`;
  3. else the governed fallback, labelled.
  
  Every value carries its source and date. **No caller passes a constant.**
- **Dividend:**
  - from the tastytrade metrics cache (`dividend_inputs`); otherwise 0, labelled `ASSUMED_ZERO:<reason>`;
  - never inherited from EV3's default;
  - DOI's `dividend_yield_available` becomes true only for a measured value.
- **IV basis:**
  - value with IV re-implied from the quoted mid on the same model and basis (`MID_IMPLIED_<model>`) when the quote is two-sided and solvable;
  - otherwise use the vendor IV, labelled `VENDOR_IV_FALLBACK`;
  - otherwise don't value (missing is never neutral).
  
  At entry, the model therefore reproduces the market by construction.

### 4.3 Migration: every pricer moves to the module (each step test-first; characterisation first)

| # | Engine | Lane | Change |
|---|---|---|---|
| M1 | Card engine (`anticipated_move` via EOD, Morning and Options Intelligence) | A | The callers pass `pricing_basis` and the mid-implied IV. The card shows the rate, dividend and IV basis it used. |
| M2 | `avshunter_options_standalone.py` `bs_value` | B | Import `price_vec` / `implied_vol_vec` / `pricing_basis`. The tool already runs from the repo's own Python environment (`avs_day.ps1`). The shortlist rules stay Lane B's own (decision D1). |
| M3 | DOI (`dividend_adjusted_black_scholes`, `contract_economics_v2`) | A | Uses the module and basis. The dividend-availability fix (§4.2). |
| M4 | Empirical EV and path engine (`black_scholes_price`, `_bs_vector`, `calibrated_iv`), also used by C12 scoring | A | Uses the module; the C12 shadow fields are versioned. |
| M5 | `scripts/compute_greeks_bs.py` (Phantom Greek backfill, local GEX store) | A | Uses `greeks_vec` with the basis rate and dividend. Existing `COMPUTED_BS` rows keep their label; recomputing them is backlog. |
| M6 | Options Intelligence `bs_price` / Greeks / `solve_iv`, the Black-Scholes part of `heston_greeks`, and `bsm_vanna_charm` | A | Uses the module. The dead `solve_iv` / `backfill_greeks_vectorised` are removed (tidy after build). The Heston integral stays for the display-only `model_atm_*`. |
| M7 | Universe scanner calls-only solver (IV rank cache) | A | `implied_vol_vec` with a dividend yield. |
| M8 | GEX `_bs_gamma` | A | `greeks_vec`. |
| M9 | `selected_contract_economics` (rate 0, dividend 0, legacy tier) | A | Uses the module and basis. |
| — | EV3 (`vanguard/ev_engine_v3.py`) | A | **Unchanged** (frozen, hidden legacy). A listed exception until C8 retires it (decision D3). |

**Guard test:** a test that scans production code and fails on any option-pricing or IV-solving function outside `domain/option_valuation.py` and the listed exceptions. This is what the OT4 test should have done.

### 4.4 Acceptance (CLAUDE.md working rules)

1. **Characterisation:** pin each migrated engine's current outputs on fixtures before changing it.
2. **Failing business-rule tests, in domain language:**
   - "A contract is priced the same in both lanes for the same inputs."
   - "At entry the model reproduces the quoted mid."
   - "The rate is the run's observed rate, with its source and date."
   - "An assumed dividend is labelled assumed, never available."
   - "No production code prices an option outside the pricing module."
3. **Against reality:**
   - rerun `g5_basis_measure.py` on the first runs after the build: entry error should be 0 by construction on solvable quotes, with the unsolvable share reported;
   - an out-of-sample check: value each contract two sessions later at the actual spot and time, current basis against the one basis, compared with the actual mid then. The one basis must be no worse on median absolute error.
4. **Regression:** the files that pin today's pricers. These are OT4, EV3, DOI-11, monetisability, the empirical EV and contract value selection tests, options analytics slices 1/2, the G4 files and the Greek backfill. Run one file per process and count failures explicitly.
5. **Run-time budget:** at most 5 minutes extra per lane. Bulk work is vectorised European; the tree runs only on material rows.

### 4.5 Not in this change

- G1/G7 (IV at exit, event crush), G2 (spreads), G3/G8 (paths, capture, predicted bid). They are built next, on this module, once for both lanes.
- Retiring EV3 or DOI (C8).
- Recomputing historical Phantom Greeks.

### 4.6 Window and effort

- **Lane A part:** pipeline code, so the Weekend window, and never during a run. Its closure artefact is the next Evening plus Morning cycle.
- **Lane B part (M2):** a Lane B tool, so it qualifies for any weekday Tonight window.
- **Effort:** about 10 production files across two sessions. Risk is medium, because it changes numbers on the card, in DOI and in Lane B's shortlist. Section 2 measures how much.

## 5. Decisions for ACK

1. **D1, Lane B shares the pricing module (recommended).** Pricing is measurement, not a lane decision, so sharing it makes the lane comparison fairer: the same contract gets the same value. The shortlist, cap and triage rules stay Lane B's own. The alternative is that Lane B keeps its own copy with a parity test, which means G1/G2/G3 later get built twice.
2. **D2, IV basis = re-implied from the mid (recommended)**, with vendor IV only as a labelled fallback.
3. **D3, EV3 stays frozen (recommended)** as a listed exception until C8 retires it. The alternative is to edit `vanguard/ev_engine_v3.py`, which breaks the Discovery/Vanguard freeze.
4. **D4, sequencing.** The measured effect of G5 on today's decisions is small (§2). The highest money items this week are G2 (spreads) and G8 (option price capture). My recommendation: build G9 + G5 first, because G2 and G1 then sit on one module for both lanes; follow straight away with G2 and G8. If you'd rather take the money items first, G2 and G8 can go ahead on today's pricers and be moved onto the module afterwards, at the cost of building them twice.
