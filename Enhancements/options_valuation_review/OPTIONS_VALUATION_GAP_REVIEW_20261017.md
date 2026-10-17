# Options valuation gap review — all pipelines

17 Oct 2026. Read-only review. **No code or configuration was changed.** Prompted by an external note (pasted by ACK) saying the options valuation "is not working as it should". Each gap below is stated against the code, with file:line references. The governing method is in `Enhancements/knowledge/03_option_valuation_and_ev.md` and `04_volatility_and_cheap_convexity.md`.

## 1. Verdict on the note

| Note's claim | Finding | Evidence |
|---|---|---|
| "Treats options as European" | **Partly wrong.** The card engine is American: a CRR tree with 300 steps (`domain/option_valuation.py:63-75`). But six other valuers in production are European BS, and four of them have no dividend term: DOI-5 / economics v2, monetisability, empirical EV, options intelligence, scanner. DOI flags early exercise as `..._EARLY_EXERCISE_NOT_MODELLED` (`domain/deterministic_option_valuation.py:220-251`). | §3 G6 |
| "Holds IV fixed" | **Correct, at every site.** The card labels it `IV_HELD at contract IV` (`domain/anticipated_move.py:234`). | §3 G1 |
| "No event crush" | **Mostly correct.** Earnings get a flat IV × 0.8 applied across the whole remaining life (`anticipated_move.py:220-240`). There is no event-variance split. | §3 G7 |
| "Values one moment, not the path" | **Correct for the card.** A path Monte Carlo exists but runs only as shadow (`empirical_option_ev.py:510-635`). It holds IV flat, uses no intraday spread, and gives no fill probability. | §3 G3 |
| "No spread model beyond half the entry spread" | **Correct.** The entry spread is reused at exit, with no widening at the open or in volatile sessions. Five cost models disagree with each other. | §3 G2 |
| "QuantLib has the American pricers" | **Not needed for that.** We already own a tested CRR tree (`tests/test_ot4_one_valuation_engine.py:50-94`, within 1% of finite differences). QuantLib is not installed. | — |
| "Capture data (recorded bids) can check it every day" | **Only partly true.** There is no intraday recorder. Option quotes are snapshots, about one per run: `option_contract_observations` holds 274,600 rows (mostly 20:00Z close plus Morning), and `exact_option_quote` holds 27,025 Morning files. | §3 G8 |
| H3 / H4 "philosophy doc" | **Not found** in the repo, memory or the docx register. Other docs use H3/H4 for other things. ACK to supply the path. | — |

## 2. Where options are valued, by pipeline

| Pipeline / stage | Engine | Model | r / q | IV | Exit friction | Status |
|---|---|---|---|---|---|---|
| Evening Phase 0 scanner | `scripts/avshunter_universe_scanner.py:814` | European BS, calls only | 0.04 / none | own bisection (when vendor null) | — | IV rank only |
| Evening 8a/8b options intel | `scripts/avshunter_options_intelligence.py:1995-2454` | BS + Heston (proxy on Windows) | 0.045 / none | vendor | — | **overwrites contract Greeks** (:4022) |
| Evening 8a/8b trade economics | `avshunter_options_intelligence.py:7068` | expiry intrinsic | — | none | none | legacy, still in CSV/Lab export |
| Evening EOD candidate (card) | `domain/anticipated_move.py` → `domain/option_valuation.py` | **American CRR** | 0.0422 fallback always / tastytrade q | vendor, held | ask+fee in, model − ½ entry spread − fee out | **live card / Lab headline** |
| Evening EOD monetisability | `contracts/selected_contract_economics.py:591` | European BS | **0 / 0** | vendor, held | none | legacy tier |
| Evening EV3 shadow | `vanguard/ev_engine_v3.py:256` | American CRR (DTE steps) | 0.045 / 0 default | vendor, ×0.85 | ±2% slippage | hidden (TC_LEGACY) |
| Evening DOI-11 | `domain/deterministic_option_valuation.py:168`, `domain/contract_economics_v2.py:61` | European BSM + q | macro rate / q from `ev3_dividend_yield_used` (likely 0 from EV3 default) | vendor ×{0.8,1,1.2} | 25 bps / min(½ spread, 15%) | ACTIVE_ADVISORY, Lab `doi_*` |
| Evening empirical EV shadow | `empirical_option_ev.py:205, 510` | European BS, no q | 0.045 | re-implied from mid (correct), held | ask in, bid out | shadow; feeds C12 and contract value selection (SHADOW) |
| Morning reprice | `morning_gate.py:1258` → same as card | American CRR | 0.0422 fallback | live contract IV, held | as card | live |
| Morning EV3 / monetisability | `morning_gate.py:4311, 4505` | as above | | | | legacy |
| Phantom backfill greeks | `scripts/compute_greeks_bs.py:48` | European BS, no q | macro JSON or 0.045 | bisection | — | stored Greeks |
| Local GEX | `macro_domain/gamma_exposure.py:44` | BS gamma | 0.04 / 0 | chain or backfill | — | display |
| C12 outcome scoring | `avshunter/c12_outcome/expression.py:90-115` | realised only (ask→EOD bid) | — | — | **no fees** | no predicted price to compare |

## 3. Gap register (ranked by accuracy impact)

**G1 — IV is flat at exit (High).** Every repricing site keeps the contract's quoted IV at the new spot and the shorter time, so there is no skew, no sticky-strike/delta rule and no term roll. The data to fix this is already stored and unused: `iv_surface_history` (ATM, median, 25Δ skew by DTE bucket; `scripts/phantom_database.py:196-212`), per-contract `chain_snapshots`, and IV per contract in `option_contract_observations`. The method is specified as σ_exit = σ₀ + β_d·ln(S_exit/S₀) + δ, with the rule stated (`knowledge/03:35`, `04:35`). The C8 engine already accepts IV per session (`domain/option_path_valuation.py:21, 157-158`), but its caller passes `None, None` (`contracts/expression_valuation_packet.py:138`). Evidence on size: in the phase 6 one-off check, the modelled exit value was 0.96× the actual exit bid for calls (IQR 0.80–1.14, n 53,921) and 0.97× for puts (IQR 0.79–1.17). The median is close, but the spread around it is wide.

**G2 — Spread / cost model (High).** Exit cost is half the *entry* spread (`option_valuation.py:82-86`). No exit spread is forecast, and spreads do not widen by time of day or VIX. Five cost conventions disagree on the same contract (EV3 ±2%; v2 min(½ spread, 15%); DOI 25 bps; empirical ask/bid; card ask+fee). The fees are approximate and still "ACK to confirm" (`config/governed_constants_v1.json:283-287`). On the evidence, this is where the money goes: entry spread ≤5% gives a mean of −2.1%, >40% gives −56.5% (`Enhancements/phase6/PH6_INTERPRETATION_20261009.md:18-29`). At the open, 11 of 26 Tier A rows lost executability on spread alone (`MORNING_REREVIEW_20260925.md`). The exit engine also values gains on **mid**, not bid (`avshunter_exit_engine.py:408-410`).

**G3 — No path, no fill probability on the card (High).** The card values a single point: the q50 session, with spot taken from a structural level (`anticipated_move.py:142-152, 221-237`). No module gives the chance that a resting +20/+30/+50% sell fills **on the bid** by day 1/2/3. The look-alikes are stock touches (`desk_card.py:64-121`, `actuarial_query.py:156-205`), terminal-value p_double (`empirical_option_ev.py:323`), and liquidity scores that are explicitly not probabilities. Assets we can reuse:
- the shadow path engine: 2,000 paths, Brownian-bridge touches, forced exit before expiry; but its innovations are pooled across 300 tickers, there is no volatility clustering, and IV is flat;
- the research replay of the ticker's own 20-session blocks (`domain/vectorized_research_ev.py`, `domain/research_path_baseline.py`), which is the only valuer on the ticker's own history.

**G4 — Heston Greeks overwrite provider Greeks (High, data accuracy). BUILT 17 Oct 2026, not yet committed. Provider Greeks are published, model Greeks are display-only `model_atm_*`, and observation history is corrected. See `G4_BUILD_RECEIPT_20261017.md`.** On Windows, `signal.SIGALRM` does not exist (`avshunter_options_intelligence.py:2274`). The calibration always falls to `_calibrate_heston_proxy` and still marks `heston_used`. `enrich_contract_with_heston_greeks` (called at :8764) then replaces the provider delta, gamma, theta and vega (:4022). The replacements are BS Greeks at ATM variance and r = 0.045, so the contract's own IV and skew are ignored. These Greeks flow into `contract_analytics` and the EV3 input checks.

**G5 — Rate and IV basis mismatch (Medium-High).**
- Six rate sources are in use (0.0422, 0.045, 0.04, 0, live macro, macro JSON).
- The card engine never receives a live rate: callers do not pass `rate` (`eod_candidate_engine.py:2887`, `morning_gate.py:1258`), so it always uses the 8 Oct fallback of 0.0422.
- Vendor IV, computed with the vendor's own r and q, is fed into our models with different r and q. The empirical engine measured the error this causes at entry (calls: median +1.2%, p90 +8.3%) and re-implies IV from the mid (`empirical_option_ev.py:478-501`). The card engine does not.

**G6 — European engines without dividends still in production (Medium).** This is where the note's "European" point does apply:
- DOI-5 / economics v2 is ACTIVE_ADVISORY and shown in the Lab as `doi_*`. It only flags early exercise.
- DOI's q comes from `ev3_dividend_yield_used`, which EV3 fills with its 0.0 default. A dividend that was never fetched may therefore read as supplied. This is plausible, not confirmed.
- Monetisability uses r = 0, q = 0.
- Empirical EV has no q, and it feeds C12 scoring.
- The only American pricer we own is CRR with a continuous yield; there is no discrete ex-dividend model.
- The exit engine has no rule for ITM, ex-dividend or early exercise (`avshunter_exit_engine.py:191-340`). This matters for ITM puts like BILI and for ITM calls ahead of an ex-date.

**G7 — Event crush (Medium).** Earnings are handled as IV × 0.8 across the whole remaining life (`anticipated_move.py:220-240`). There is no total-variance minus diffusive-variance split and no post-event IV. The method is specified in `knowledge/04:37-41` and recommended in `MODEL_RESEARCH_ASSESSMENT_20260925.md:91-101`. The options-intelligence "IV crush" is a fixed 10-vol-point vega score (:7183).

**G8 — No predicted option price per session and no forecast-vs-realised check (Medium).**
- The card publishes returns conditional on spot (target / stall / invalidation at q50), not a predicted bid by session.
- C12 scores realised P&L only, with no fees.
- `doi_outcome_labels` and `doi_probability_models` have **0 rows**: the session-level bid-hurdle label was built but has never run (`domain/dynamic_options_outcomes.py:145-146`).
- There is no intraday option recorder. `bridge/tastytrade_go_quote_capture.py` exists, but no output was found. The MarketData feed is 15 minutes delayed.

**G9 — Engine sprawl (Low, but blocks G1–G8).**
- There are seven copies of European BS and three IV solvers, each with different time and friction conventions.
- `tests/test_ot4_one_valuation_engine.py` enforces "one engine" for the card only: it does not scan for other pricers.
- The legacy expiry-intrinsic payoffs (`option_gain_at_target`, `max_convex_r_multiple`) are still written to the CSV and Lab export.
- Options-intelligence `solve_iv` / `backfill_greeks_vectorised` is dead in production. Its docstring claims EV3's missing IV is solved there, but it is not, so null vendor IV still produces `REJECT_UNIT_IV`.

## 4. What we already own (reuse before building)

| Need | Existing owner |
|---|---|
| American pricer | `vanguard/ev_engine_v3.py:256` CRR via `domain/option_valuation.py` (tested) |
| Path engine with touches | `empirical_option_ev.py:510-635` (shadow) |
| Ticker's own price history paths | `domain/research_path_baseline.py`, `domain/vectorized_research_ev.py` |
| IV path slot | `domain/option_path_valuation.py` `PathSession.implied_vol` |
| IV surface / skew / term data | `iv_surface_history`, `chain_snapshots`, `option_contract_observations` |
| Quote history for calibrating spread and checking forecasts | `option_contract_observations` (274,600 rows, 28 Aug–15 Oct), `market_observations/exact_option_quote` |
| IV re-implied on our own basis | `empirical_option_ev.py:478-501` |
| Realised outcome scorer | `avshunter/c12_outcome/expression.py` |
| Bid-hurdle realised label | `domain/dynamic_options_outcomes.py` (built, 0 rows) |

## 5. Suggested order (each needs an approved root cause and design first; CLAUDE.md working rules)

1. **G4** Heston Greek overwrite: a data-accuracy defect, small and contained.
2. **G5 + G9** one rate source, one IV basis, one BS. This prepares the ground for everything after it.
3. **G2** spread model calibrated on `option_contract_observations`, with time of day and IV/VIX regime, applied at exit on the bid.
4. **G1 + G7** IV at exit from the stored surface (β_d fitted per ticker or sector, sticky rule stated), plus the event-variance split.
5. **G3 + G8** extend the shadow path engine: the ticker's own blocks, the IV path, and the spread path. Publish the predicted bid by session and P(fill) for +20/+30/+50% by days 1–3. Score it daily against recorded quotes (populate `doi_outcome_labels`), and start an intraday quote recorder so fills can be judged on the bid.
6. **G6** exit-engine rules for ITM puts and ex-dividend dates; discrete dividends in CRR.

Confidence: High on what the code does (the key claims were re-checked in source). Medium on how much each gap moves outcomes, until it is measured against recorded bids.
