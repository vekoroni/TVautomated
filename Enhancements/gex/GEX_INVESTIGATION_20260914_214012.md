# GEX investigation — run 20260914_214012 (16 Sep 2026)

Read-only investigation. No pipeline code changed. Evidence: `evidence/gex_recompute_20260914.py` (replica of the pipeline logic + independent recompute) and `evidence/gex_recompute_20260914.csv` (126 tickers).

## Verdict

GEX outputs are not valid as GEX.

- **Per-ticker GEX (drives decisions):** the formula is roughly right, but the **gamma flip algorithm is wrong** and the walls are OI walls, not GEX walls. EIL then **synthesises its own GEX map** from hard-coded anchors.
- **Market-level SPY/QQQ GEX:** the formula is correct but it **does not deliver**. Every run row is UNKNOWN/null, and one consumer substitutes a neutral 0.5.

## 1. Producers

| Producer | Entry | Status 20260914 |
|---|---|---|
| `scripts/avshunter_options_intelligence.py` `compute_gex` (L2996), `compute_oi_walls` (L3155), called L7020–7039 | orchestrator `run_options_intelligence` | Runs. `gamma_flip`, `gamma_flip_conf`, `gamma_flip_gap_pct`, `call_wall`, `put_wall`, `max_pain`, `gamma_island_*`, `gamma_velocity_*` |
| `execution_intelligence.py` `_synthesise_gex_map` (L255–323) + `vanguard/execution/strategies/gex_flipper.py` | `execution_intelligence_runner.py` | Runs. `eil_gex_regime`, `eil_gex_score`, size penalty |
| `orchestrator/completed_session_gex.py` → `scripts/build_local_gex.py` → `macro_domain/gamma_exposure.py` → `canonical_data/macro_gex_overlay.py` | orchestrator L4700–4731 | **UNAVAILABLE** for 20260913 and 20260914 |
| `scripts/phantom_gamma_field.py` L32–68 | phantom phase | Runs; "net_gex_proxy" = Σγ·OI·sign (no spot, no ×100) |

The replica matched the published flip, call wall and put wall on 100% of 126 tickers. The input data is used faithfully; the defects are in the logic.

## 2. Per-ticker defects

| ID | Defect | Evidence |
|---|---|---|
| **GEX-D1** (root) | Flip = **first sign change of per-strike GEX scanning from the lowest strike** (L3016–3024). There is no spot re-pricing and no cumulative GEX. Chains reach ~0.38× spot, so the "flip" is usually a deep OTM strike. | Published distance from spot: median 22.3%, p90 64.6%; 26% of flips < 0.5× spot. Correct grid re-priced flip: median 5.5%, p90 21.5%. NVDA 16.05 vs 207.6 (spot 210.96); TSLA 107.9 vs 356.1 (358.97); AAPL 94.6 vs 306.7 (333.08); IWM 110.8 vs 299.5 (287.91). "Spot above flip = positive gamma" disagrees with the true net GEX sign 22% of the time. |
| GEX-D2 | Units γ·OI·100·spot instead of γ·OI·100·spot²·0.01; no net GEX published. | L3008. Magnitudes not comparable across tickers. |
| GEX-D3 | `gamma_flip_conf` is an ad-hoc density score, but is consumed as dealer wall defence. | L3027–3034; `wall_break_scorer.py` L219–221; `catastrophe_gate.py` L349 |
| GEX-D4 | Walls = max **OI** across all expiries ≤ 110 DTE, with no side-of-spot constraint. | Only 44% of call walls / 48% of put walls equal the max-GEX strike. 139/921 CALL rows have the call wall below spot; 94/395 PUT rows have the put wall above spot. |
| GEX-D5 | Gamma velocity measures distance to the bogus flip. | L3217; MOVING_AWAY 617, DISTANT 496 |
| GEX-D6 | Gamma = 0 on 11% of rows (deep ITM, IV placeholder 0.0001). `backfill_greeks_vectorised` (L2318) is never called. | Provider gamma otherwise fine (IV decimal, median 0.59) |

## 3. EIL synthetic GEX

| ID | Defect | Evidence |
|---|---|---|
| **GEX-D7** | `_synthesise_gex_map` invents exposures: call wall +2.5M, put wall −2.5M, ±750k either side of flip, ±600k at spot from put/call OI ratio. The regime reflects wall geometry, not dealer gamma. | Agrees with the true sign 79/110 (16 of 126 NEUTRAL). NVDA labelled AMPLIFYING while true net GEX = +$196M per 1%. The fake anchors create crossings near spot: 495 rows AT_FLIP, 436 of them with a published flip > 3% away. |
| GEX-D8 | Scale bug: `_dynamic_size` L179 applies 0.6× when `gex_proximity_pct < 0.3`. The value is a fraction, so the test means "within 30%". | 706/1,449 rows qualify on published gap alone |

## 4. Market-level SPY/QQQ

| ID | Defect | Evidence |
|---|---|---|
| **GEX-D9** | `canonical_data/marketdata_option_chain.py` L88–89 always sends `date=session_date`; MarketData rejects this for the current day. | 20260914 error "The date parameter is used for historical queries only". 20260913: HTTP 400, no detail (cause unverified). |
| GEX-D10 | Missing GEX becomes neutral: `regime_consensus.py` L240–243 sets `gex_regime_score` = 0.50. | Run rows: `gex_regime_score` 100% null, `dealer_gamma_state` 100% UNKNOWN, `gamma_risk_flag` always 0, `usmi_gamma_position` UNAVAILABLE. `avshunter_gex_proxy.csv` 10 days stale (09-04); macro JSON gex extras unavailable ("coverage 77.7% < 80%"). |

The formula in `macro_domain/gamma_exposure.py` is correct: γ·OI·100·S²·0.01, calls + / puts −, grid flip, GEX walls. The last manual output (2026-09-04) was sensible: SPY net +$1.66B per 1%, flip 766 vs spot 770. Note: macro was removed from pipeline decisions by owner decision, so this path's value is context only.

## 5. Consumers whose decisions change

| Consumer | Effect |
|---|---|
| `execution_gate.py` L371–398 | 0.75× when spot > flip, which is 81.6% of rows because of D1. Runway falls back to the flip and uses `abs()`, so a put wall above spot counts as runway. |
| `wall_break_scorer.py` | F3 rewards a larger flip gap (L231, norm 50; 26% of rows get the full 20); F2 uses D3. WBS → `eod_candidate_engine` (15% weight + grade); Lab target falls back to `wbs__wall_price` (`lab_control.py` L2872). |
| `catastrophe_gate.py` | Gap and conf used as proximity factors |
| `avshunter_exit_engine.py` L333–346 | CALL > 0.5% above call wall → EMERGENCY_EXIT. Fires immediately when the wall is below spot (D4). |
| `avshunter_monetisation_policy` | `SOFT_GAMMA_TIGHT = 0.25` compared with a percent gap (8 rows); test fixtures use fractions, so units are ambiguous |
| `mcmillan_advisory_layer._gex_bucket` | Prefers synthetic `eil_gex_regime` (D7) |
| `eil_size_multiplier` | Appears advisory (test fixtures only in `position_sizing_engine`). Run values: median 0.0, mean 0.19. EIL verdicts: BLOCKED 1,062, NOT_EVALUATED 255, EXECUTE_WITH_CAUTION 75, EXECUTE 41, WATCHLIST 16. |

## 6. Correct fix design (not implemented, awaiting approval)

Place this in the **Market Structure / Volatility** contexts of the rebuild, not as a patch on the old path.

1. **One GEX engine.** Reuse `macro_domain/gamma_exposure.calculate_gamma_exposure` for tickers: explicit DTE scope; provider gamma, with a Black-Scholes fallback only where gamma/IV is missing, flagged as such.
2. **Published per-ticker fields:** `net_gex_usd_1pct`, call/put GEX, GEX call wall above spot and GEX put wall below spot (OI walls kept under their own names), `gamma_flip` from grid re-pricing (null when there is no crossing, never a fallback strike), `dealer_gamma_regime`, coverage/quality state. Replace `gamma_flip_conf` with a real wall concentration metric.
3. **Retire** `_synthesise_gex_map`; any consumer reads published net GEX and flip. Fix the proximity units.
4. **Adapter:** omit `date` for the current session (ET); use it only for historical sessions. Missing GEX → explicit `GEX_UNAVAILABLE`, never 0.5.
5. **Consumers:** re-base WBS F2/F3, catastrophe gate, execution gate and exit Trigger 5 on the new fields — or retire them if the rebuild's ranking replaces them. Resolve percent-vs-fraction units.
6. **Assurance tests:** flip within a sane band of spot, or null; walls on the correct side of spot; SPY/QQQ sign and magnitude checked against a reference; replica-vs-published reconciliation on every run.
7. **Validation before authority:** GEX regime must show it improves first-passage or expression outcomes (Knowledge note 06) before it can influence ranking.

## 7. `scripts/build_local_gex.py --session latest-completed` (owner: "this is what should be running")

| # | Finding | Evidence |
|---|---|---|
| L1 | The script **does calculate GEX correctly**, but only for **SPY and QQQ**, and only from chains already in Phantom (`provider_requests: 0`). | `build_local_gex.py` L55–130, default `--tickers SPY,QQQ`; `macro_domain/gamma_exposure.py` |
| L2 | **`latest-completed` has no freshness check.** It picks the latest date on which both SPY and QQQ exist in Phantom and reports `status: COMPLETE`. The last manual run (14 Sep 21:31, `LOCAL_GEX_20260914_213128`) produced GEX for **4 Sep**, 10 days stale, labelled COMPLETE. | `gamma_exposure_store.py` `latest_common_session`; `dropbox/market_data/avshunter_gex_run_manifest.json` `session_date 2026-09-04` |
| L3 | **No SPY/QQQ chains reach Phantom after 4 Sep.** SPY has only 4 dates in Phantom (07-31, 08-28, 09-03, 09-04); the 09-03 rows (5,284) have gamma and IV null on every row. SPY/QQQ are not in the evening candidate chain folder. The weekly Phantom backfill (source `marketdata.app`) last wrote 09-04 (last greeks audit 05 Sep), so the 11 Sep weekly snapshot did not run. | Phantom `chain_snapshots`; `options_greeks_run_audit` |
| L4 | **The dedicated evening refresh fails at acquisition,** so it never projects SPY/QQQ or calls this script. 14 Sep: `HTTP 400 (Invalid date. The date parameter is used for historical queries only.)` because `marketdata_option_chain.py` L88 always sends `date`. 13 Sep run (session 09-11, a past date): `HTTP 400` with no detail, cause unverified. | `data/output/runs/20260914_214012/macro/completed_session_gex_refresh_*.json`; `…/20260913_143230/…` |
| L5 | **Even when it works, nothing per-ticker uses it.** Output goes to `dropbox/market_data/avshunter_gex_proxy.csv` and the macro overlay (macro is context-only by owner decision). The per-ticker pipeline (`compute_gex` in options intelligence, EIL `_synthesise_gex_map`) never calls `calculate_gamma_exposure`; it uses its own defective calculation (§2–3). | imports: only `orchestrator/completed_session_gex.py` and `scripts/refresh_macro_context.py` call `build_local_gex` |
| L6 | A manual CLI run does not apply the macro overlay (only the orchestrator path calls `apply_completed_gex_overlay`), so `macro_intelligence_latest.json` keeps `gex_regime_score = None` even after a manual run. | `completed_session_gex.py` L124–129 vs `build_local_gex.py main()` |

**Root cause in one line:** the correct GEX engine exists but is (a) starved of data, because SPY/QQQ acquisition fails and the weekly backfill stopped, (b) silently reporting stale data as COMPLETE, and (c) wired only to the macro side-channel, never to the per-ticker decision path.

**Fix design additions (not implemented):**
1. Acquisition: omit `date` for the current completed session (live end-of-day chain); use `date` only for past sessions. Diagnose the 09-11 HTTP 400 with a minimal request (needs owner approval; MarketData charges credits per contract returned).
2. Freshness: `build_local_gex` must require the expected evidence session. If the latest common session is older, return `STALE` (never COMPLETE) and name the session found.
3. Restore or replace the weekly Phantom snapshot job (stopped after 04 Sep) and add SPY/QQQ to the fixed IV/chain panel (see `../iv_history/`).
4. Per-ticker: run the same `calculate_gamma_exposure` engine over the daily canonical chains for every candidate ticker (fix design §6.1–6.2) instead of `compute_gex`.
5. The CLI should either apply the overlay or state in its manifest that it did not.

## Not verified

- Cause of the 20260913 HTTP 400 (no detail logged; no API calls made).
- The as-of date of the open interest (the chain has no OI timestamp; OI is normally prior day).
- SPY/QQQ are not in the per-ticker chain folder, so there was no per-ticker recompute for them.
- Whether the root `zero_dte_screener` / `obi_predictor` GEX code runs in any scheduled job.
