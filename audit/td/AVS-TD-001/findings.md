# AVS-TD-001 — Discovery findings (AVS-DISC-002)

**RESEARCH_ONLY.** Nothing in this file authorises, sizes, clears or recommends a position (Rule 13). Discovery describes and measures (Rule 9). No verdict terms and no severities. Upper-case tokens in backticks are pipeline field values quoted as data.

**Run condition for every entry.** No NORMAL_COMPLETED_SESSION run exists; every stored run is TEST condition. Reference runs 20260911_115904 (primary) and 20260910_150045 (comparison) come from pre-remediation code 00baa2b. Performance-type numbers use historical sources only (Rule 10): outcomes are retrospective reconstructions from daily OHLC (`db_copies/historical_prices.sqlite`) on presented-not-taken candidates. There are no fills (`FillRecorded` = 0) and the ledger has 0 resolved outcomes. Stored books are read for structure only. Any cell with n < 100 is marked `INSUFFICIENT_POWER (n=…)` and is not presented as a result (Rule 12).

**Numbering.** DISC-F01…DISC-F75 in track order: M1, M2, M3, M4, M5, M6, M7, M8, M9. The track placeholder ID is kept in brackets. The outcome census counts populations and states no findings, so it has no entry. TRACE lines are copied from the tracks.

---

## M1 — Money to follow
Data source: price store copy `ohlcv_daily` (3,618 tickers, 2021-08-23 → 2026-09-10); macro snapshots and USMI packets for labels; stored books and the ledger copy for structure only.

### DISC-F01 [DISC-F-M1-1] — Cross-sectional dispersion
- **Measured:** per-session cross-sectional std of forward h-session log returns, pipeline universe.
- **Data:** `ohlcv_daily`, 2024-01-01 → 2026-09-10, today's pipeline membership applied (market history, no run condition).
- **Number:** 5-session std p10/p50/p90 = 0.0551 / 0.0678 / 0.0869; IQR p50 0.0538. 10-session p50 0.0957; 20-session p50 0.1369. Full store h=5 p50 0.0709.
- **n:** 670 sessions (median 1,722 tickers per session).
- **CALL / PUT / OTHER:** not direction-split; thesis-set dispersion by direction `INSUFFICIENT_POWER (n=1 session per run)`; stored-run window `INSUFFICIENT_POWER (n=30 sessions)`.
- **Does not establish:** that the dispersion can be captured, predicted or monetised through options; freedom from survivorship (today's membership applied back to 2024) or bad prints (no clipping; IQR and 90–10 are the robust readings).
- `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670`

### DISC-F02 [DISC-F-M1-2] — Within-sector dispersion
- **Measured:** 5-session within-sector std p50 per GICS sector, derived ticker→sector map.
- **Data:** `ohlcv_daily` + `p21_M1_sector_map.csv`; window as DISC-F01.
- **Number:** among sectors with median constituents ≥ 100, 0.0470 (Financials) to 0.0805 (Health Care); Information Technology 0.0787; all-universe 0.0678. Real Estate (n=90), Materials (n=87), Consumer Staples (n=68), Communication Services (n=56), Utilities (n=46) are `INSUFFICIENT_POWER` and not presented.
- **n:** 670 sessions per sector.
- **CALL / PUT / OTHER:** not direction-split.
- **Does not establish:** that sector membership explains returns; that sector-neutral selection beats the universe; GICS mapping quality beyond the 1.000 agreement between two internal sources.
- `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670`

### DISC-F03 [DISC-F-M1-3] — Sector relative-strength persistence
- **Measured:** autocorrelation of 5-session equal-weight sector RS, cross-sector median over 11 sectors.
- **Data:** `ohlcv_daily` + derived sector map, 2024-01-01 → 2026-09-10.
- **Number:** lag 5 / 10 / 20: −0.041 / −0.002 / 0.012; non-overlapping lag 5 −0.092 (store −0.074; ETF −0.064). Lag 1 0.793 is the mechanical overlap of 5-session windows; 1-session RS lag 1 is −0.000. Approximate 95% zero band ±0.075 (675 sessions), ±0.17 (135 blocks).
- **n:** 675 sessions × 11 sectors.
- **CALL / PUT / OTHER:** not direction-split.
- **Does not establish:** absence of persistence at industry or theme level, at other windows, conditional on regime, or in non-linear form. Composites are equal-weighted.
- `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_rs_autocorr.csv | N=675`

### DISC-F04 [DISC-F-M1-4] — Stored macro→ticker join carries no routing information
- **Measured:** population of the USMI alignment fields.
- **Data:** primary Lab book 20260911_115904, comparison book 20260910_150045 (structure, TEST); ledger copy.
- **Number:** primary `usmi_sector_alignment` = NEUTRAL 1,444/1,444; `usmi_alignment_reason` = `SECTOR_UNMAPPED` 1,444/1,444 although `gics_sector` is filled 1,444/1,444; `usmi_alignment_priority` fill 0.000; four-label vocabulary 0 occurrences in primary CSVs. Comparison UNAVAILABLE 1,424/1,424. Ledger NEUTRAL 3,358 / UNAVAILABLE 2,958 / null 1,974.
- **n:** 1,444; 1,424; 8,290 events.
- **CALL / PUT / OTHER:** 798 / 458 / 188, all NEUTRAL.
- **Does not establish:** why the join produced NEUTRAL (Track F); post-remediation behaviour; label skill.
- `TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-final_opportunity_book_20260911_115904.csv:usmi_sector_alignment,usmi_alignment_reason,usmi_alignment_priority | N=1444`

### DISC-F05 [DISC-F-M1-5] — Label history too short to measure routing skill
- **Measured:** depth of dated routing-label history and forward sessions available.
- **Data:** `macro_snapshot.json` for 27 runs; 4 dropbox USMI packets; `ohlcv_daily` to 2026-09-10.
- **Number:** four-label routing exists for one as-of session (2026-09-11, 2 revisions): 19 route observations, 15 mappable, 0 forward sessions. Priority lists cover 3 as-of sessions; snapshot bias/lead/avoid labels cover 13. Largest label×h cell n=51, so every hit-rate cell is `INSUFFICIENT_POWER (n≤51)`. n ≥ 100 at h=5 would take roughly 17–100 packet sessions per four-label value.
- **n:** 686 panel rows (332 distinct).
- **CALL / PUT / OTHER:** four-label CALL 8 (7 mapped), PUT 11 (8 mapped); OTHER not applicable.
- **Does not establish:** that routing labels have or lack predictive value; proxy families are not USMI routing.
- `TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_usmi_labels.csv | N=686`

---

## M2 — Forecast vs implied volatility
Data sources: outcomes `ohlcv_daily` (bars strictly after the forecast session); forecasts `garch_forecasts_<run>.csv` on 22 TEST runs 2026-07-23 → 2026-09-11; IV from `iv_surface_history` (weekly), `options_greeks_history`, `iv_history_cache.db` and the pipeline's own IV; books for bucket labels only. C9 is unmet (no validation report exists), so ALG-10 diagnostics are derived by the track.

### DISC-F06 [DISC-F-M2-1] — Forecast coefficient on realised |return| given matched IV
- **Measured:** OLS of |ln(S_{d+h}/S_d)| on F_h and IV_h; coefficient b_F.
- **Data:** `ohlcv_daily` + `iv_surface_history` ATM IV (0–5 sessions stale; bucket `8_30` serves h=10 and h=20) + `garch_forecasts`; one row per (ticker, session).
- **Number:** pooled b_F 0.192 / 0.313 / 0.196 at h=5/10/20 (t_HC1 3.76 / 6.21 / 4.72; session-clustered t 2.72 / 9.60 / 7.65). b_IV 0.486 / 0.181 / 0.206. Robustness: averaged IV at h=5 b_F 0.076 (t 1.57); greeks-chain IV at h=20 b_F 0.021 (t 0.25).
- **n:** 2,389 / 2,935 / 2,931 (non-overlapping 1,300 / 1,835 / 1,506); 3–6 session clusters.
- **CALL / PUT / OTHER:** CALL b_F 0.353 / 0.331 / 0.262 (t 3.40 / 4.45 / 4.49). PUT 0.128 / 0.039 / −0.016 (t 0.76 / 0.42 / −0.14; n 253 / 272 / 270). OTHER 0.136 / 0.333 / 0.135 (t 2.32 / 4.65 / 2.46; clustered 1.83 / 5.28 / 1.14).
- **Does not establish:** that the forecast holds information the options market lacks. The IV proxy is weekly, stale and tenor-mismatched, and IV measurement error shifts weight onto the correlated forecast (corr 0.75). 3–6 clusters over 7 weeks. Nothing about option P&L, edge or tradability.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_regressions.csv,p22_M2_robustness.csv | N=2389/2935/2931`

### DISC-F07 [DISC-F-M2-2] — Forecast alone vs IV alone (R²)
- **Measured:** R² of |return| on F alone and IV alone, common sample.
- **Data:** as DISC-F06, across IV sources.
- **Number:** surface IV vs F: h=5 0.238 vs 0.183; h=10 0.140 vs 0.159; h=20 0.118 vs 0.115. Cache and greeks IV higher than F at every h; pipeline IV lower at every h (h=5 0.092 vs 0.143).
- **n:** surface 2,389 / 2,935 / 2,931; pipeline 8,062 / 5,156 / 2,237.
- **CALL / PUT / OTHER** (surface, R² F / IV): h=5 CALL 0.240/0.254, PUT 0.135/0.208, OTHER 0.163/0.225; h=10 0.161/0.137, 0.071/0.119, 0.175/0.155; h=20 0.140/0.130, 0.049/0.099, 0.089/0.100.
- **Does not establish:** level calibration of either input; R² differences between sources reflect IV measurement quality as much as information.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_regressions.csv | N=2389/2935/2931`

### DISC-F08 [DISC-F-M2-3] — Forecast level against realised volatility (ALG-10 form)
- **Measured:** median RV_h/σ_f and coverage_1σ.
- **Data:** `ohlcv_daily` + `garch_forecasts`, deduplicated; 13 forecast sessions 2026-07-22 → 2026-09-01.
- **Number:** median ratio 0.697 / 0.719 / 0.800 (IQR 0.420 / 0.346 / 0.347); coverage_1σ 0.803 / 0.822 / 0.782 vs 0.68 nominal; mean F / mean |r| 1.61 / 1.67 / 1.59 vs 1.25 for an unbiased normal forecast.
- **n:** 17,275 / 13,460 / 5,172.
- **CALL / PUT / OTHER:** CALL 0.704 / 0.720 / 0.794 (n 9,106 / 8,831 / 3,255); PUT 0.677 / 0.705 / 0.845 (n 1,837 / 1,567 / 495); OTHER 0.695 / 0.724 / 0.796 (n 6,332 / 3,062 / 1,422).
- **Does not establish:** a stable bias. 7 weeks of falling realised vol; close-to-close RV omits intraday range; coverage partly reflects fat tails.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_alg10.csv | N=17275/13460/5172`

### DISC-F09 [DISC-F-M2-4] — Forecast above market IV
- **Measured:** median σ_f/IV per IV source.
- **Data:** surface, cache, greeks, book `atm_iv` (runs from 20260831), pipeline IV; `garch_forecasts`.
- **Number:** surface `0_7` 1.254 (n=4,560); surface `8_30` 1.146 (n=13,919); cache 1.156 (n=13,210); greeks 1.08–1.10 (n=1,893); book `atm_iv` 1.138, σ_f > IV on 72% (n=4,350); pipeline IV 1.118 (n=14,279). Over the same windows mean IV / mean |r| is 1.43–1.87.
- **n:** 1,893–14,279 per source.
- **CALL / PUT / OTHER:** pooled, not direction-split.
- **Does not establish:** whether "20–40% above IV" holds for any contract; the proxies are ATM snapshots, not the contract priced.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_gapfields.csv | N=14279`

### DISC-F10 [DISC-F-M2-5] — Forecast/realised ratio drifts across sessions
- **Measured:** per-session median σ_f/RV and coverage_1σ.
- **Data:** `ohlcv_daily` + `garch_forecasts`, one retained run per session.
- **Number:** h=5 median σ_f/RV 1.126 (07-22) to 1.747 (08-19), sd 0.190; coverage 0.586 → 0.932. h=10 1.048–1.573 (sd 0.157); h=20 1.055–1.388 (sd 0.144). Median σ_f stays 0.46–0.52 while RV_5 falls 0.42 → 0.27.
- **n:** 13 / 10 / 4 sessions; each session cell ≥ 1,248 rows.
- **CALL / PUT / OTHER:** not direction-split.
- **Does not establish:** a trend, regime rule or seasonality; 13 overlapping sessions in one summer.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_stability.csv | N=13 sessions`

### DISC-F11 [DISC-F-M2-6] — Per-hidden-state multiplier, time-ordered split
- **Measured:** test-partition median ratio and |log ratio| after an overall vs per-state multiplier (clipped train median RV/σ_f).
- **Data:** `ohlcv_daily` + `garch_forecasts` + book `hidden_state`; train before 2026-08-15, test on/after.
- **Number:** h=5 test median per-state 0.812 vs overall 0.818 (|log ratio| 0.320 vs 0.315); h=10 0.840 vs 0.851 (0.249 vs 0.240). Neither reaches [0.90, 1.10]. h=5 COMPRESSED_BALANCED 0.702, LOW_ENERGY_NO_EDGE 0.700, COMPRESSED_BEARISH_FORCE 0.603 (n=108). TRENDING_BULLISH_INERTIA, COMPRESSED_BULLISH_FORCE, TRENDING_BEARISH_INERTIA `INSUFFICIENT_POWER (n=93, 28, 18)`.
- **n:** train 6,087 / test 4,891 (h=5); test 4,320 (h=10).
- **CALL / PUT / OTHER:** not direction-split.
- **Does not establish:** that a per-bucket correction can never help; only 2 states testable, `phase` absent before 20260831, test windows 7 (h=5) and 4 (h=10) sessions.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_state_correction.csv | N=6087 train/4891 test`

### DISC-F12 [DISC-F-M2-7] — `l3_expected_move_6_10d < l3_expected_move_1_5d` on every row
- **Measured:** share of rows where the 6–10d expected move is below the 1–5d move.
- **Data:** `garch_forecasts_<run>.csv`, 22 TEST runs.
- **Number:** 100.000% of rows in every run; ratio 0.4142 (range 0.4111–0.4176). `_1_5d` = σ_f·√(5·5/7/252)·100 (median ratio 1.000000).
- **n:** 29,925.
- **CALL / PUT / OTHER:** 13,216 / 3,491 / 13,218, all 100%.
- **Does not establish:** which consumers misread the field.
- `TRACE: REQ-NONE | ALG-01 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-garch_forecasts_<run>.csv | N=29925`

### DISC-F13 [DISC-F-M2-8] — Pipeline-published forecast-vs-IV fields
- **Measured:** definition, producer and population.
- **Data:** books from 20260831 (structure), `garch_forecasts`, source.
- **Number:** the only such field is `garch_iv_tailwind_score` = IV − σ_f (`layer3_forward_variance.py:531`), book median −0.0445. Its IV input is the last-row `implied_vol`/`contract_iv` (`garch_runner.py:190`), not book `atm_iv`; the two agree within 0.01 on 33.5% of rows. Missing IV written as 0.0 on 12,141 of 29,925 rows. `iv_vs_hv` compares IV with 30-day historical vol, not the forecast.
- **n:** 4,759 book rows; 29,925 forecast rows.
- **CALL / PUT / OTHER:** not direction-split.
- **Does not establish:** how downstream scoring uses these fields.
- `TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_gapfields.csv | N=4759`

---

## M3 — When we were right, what were we right about
Data sources: labels `probes/p32_labels.csv` (retrospective ALG-08 labels, vol-budget target S·(1 ± 1.5·σ_a·√(h/252))) from 15 TEST books (decision sessions 2026-07-22 → 2026-09-01), presented-not-taken; contract geometry and entry quote from books (structure); option paths `options_greeks_history` (5 sparse snapshot dates). UNGOVERNED_PRE = 12 books before 20260831; GOVERNED = 3 books. p32 has no OTHER rows, so OTHER is `INSUFFICIENT_POWER (n=0)` throughout.

### DISC-F14 [DISC-F-M3-1] — Direction vs thesis amount
- **Measured:** terminal side correct; TARGET_FIRST_V; median MFE vs median vol-budget distance.
- **Data:** p32 labels, unique theses.
- **Number:** side correct CALL 45.4% / PUT 53.5%; TARGET_FIRST_V 6.6% / 3.4%; median MFE 4.1% / 4.4% vs vol-budget distance 13.8% / 14.2%.
- **n:** 8,417.
- **CALL / PUT / OTHER:** CALL 6,900; PUT 1,517; OTHER `INSUFFICIENT_POWER (n=0)`. UNGOVERNED CALL 11–20 `INSUFFICIENT_POWER (n=35)`; PUT 11–20 `INSUFFICIENT_POWER (n=6)`.
- **Does not establish:** that the vol-budget target is the right thesis amount; anything about taken trades; edge against a base rate.
- `TRACE: REQ-NONE | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_thesis_outcomes.csv | N=8417`

### DISC-F15 [DISC-F-M3-2] — Four-cell mass: side correct × monetised
- **Measured:** share of priced theses per side_correct × monetised_125 cell (best in-window snapshot bid ≥ 1.25 × entry ask).
- **Data:** p32 + books (entry ask) + `options_greeks_history` (median 1 snapshot per window).
- **Number:** side-wrong/not monetised 50.7%; side-correct/not monetised 37.8%; side-correct/monetised 10.9%; side-wrong/monetised 0.6%. Among side-correct theses 77.7% did not reach 1.25×.
- **n:** 1,250 priced.
- **CALL / PUT / OTHER:** CALL (792) 53.3 / 37.1 / 9.0 / 0.6%, side-correct not monetised 80.5% (294/365). PUT (458) 46.3 / 39.1 / 14.2 / 0.4%, 73.4% (179/244). GOVERNED side-correct subsets `INSUFFICIENT_POWER (n=60, n=50)`. OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** that theses never reached 1.25× between snapshots (lower bound); the rate on the 85% unpriced; fill feasibility.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=1250`

### DISC-F16 [DISC-F-M3-3] — What stopped side-correct theses monetising
- **Measured:** first-binding cause (probe-imposed order) and multi-cause incidence, side-correct not-monetised priced theses.
- **Data:** as DISC-F15, UNGOVERNED books.
- **Number:** CALL first-binding: MFE < strike distance 26.5%; flat decay ≥ 25% 25.3%; none identified 20.9%; IV down ≥ 10% 17.3%; spread > 15% 10.0%. PUT: MFE < strike 30.5%; flat decay 27.7%; reach > 1.5σ 14.2%; IV 13.5%; spread 7.1%; none 7.1%. Incidence: flat decay 72.3% / 66.0%; reach > 1.5 on 70.2% of PUT; mean causes 1.68 / 2.18.
- **n:** 390 (CALL 249, PUT 141).
- **CALL / PUT / OTHER:** GOVERNED CALL `INSUFFICIENT_POWER (n=45)`; GOVERNED PUT `INSUFFICIENT_POWER (n=38)`; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** causality (causes co-occur; order imposed); IV crush on a daily path; the right decay threshold; GOVERNED attribution.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=390`

### DISC-F17 [DISC-F-M3-4] — Side-wrong theses: invalidation touch and loss beyond stop
- **Measured:** touch share among side-wrong theses; terminal loss ÷ stop distance on touched theses.
- **Data:** p32 labels, UNGOVERNED.
- **Number:** touched CALL 71.8%, PUT 63.7%; on touched theses loss exceeds the stop on 62.0% / 57.0%, median loss/stop 1.24 / 1.15. Median stop distance 3.0% touched CALL vs 6.0% timeout-negative CALL.
- **n:** 4,304 (CALL 3,657, PUT 647).
- **CALL / PUT / OTHER:** GOVERNED CALL `INSUFFICIENT_POWER (n=60, n=48)`; GOVERNED PUT `INSUFFICIENT_POWER (n=18, n=41)`; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** the fill at the stop (gap-through not measured on daily bars); option P&L of stopping out; anything GOVERNED.
- `TRACE: REQ-NONE | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_thesis_outcomes.csv | N=4304`

### DISC-F18 [DISC-F-M3-5] — Contract usability and option-history coverage
- **Measured:** share of theses with a usable selected contract; share priceable.
- **Data:** books (structure) + `options_greeks_history`.
- **Number:** UNGOVERNED selected contract unusable on 78.9% (6,412/8,128). Coverage: no symbol 3,356; no entry ask 1,811; opposite-side symbol 1,247; no snapshot 725; symbol absent 28; priced 1,250 (14.9%, on 3 snapshot dates).
- **n:** 8,417.
- **CALL / PUT / OTHER:** usable UNGOVERNED CALL 17.0% (1,141/6,728), PUT 41.1% (575/1,400); GOVERNED 99.4% / 99.1%; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** whether a valid contract existed in the chain; why the book fields are empty.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=8417`

### DISC-F19 [DISC-F-M3-6] — Monetisation rate by condition and horizon
- **Measured:** monetised_125 rate and median best bid / entry ask.
- **Data:** as DISC-F15; GOVERNED priced at 09-04, UNGOVERNED at 07-31 and 08-28.
- **Number:** GOVERNED 1–5 CALL 10.9%, PUT 11.3%; UNGOVERNED 6–10 CALL 11.0%, PUT 16.8%; UNGOVERNED CALL 1–5 3.0%. Median bid/ask below 1 in every cell (0.32–0.81).
- **n:** 1,250; cells GOVERNED CALL 156, GOVERNED PUT 106, UNGOVERNED CALL 6–10 498, UNGOVERNED PUT 6–10 304, UNGOVERNED CALL 1–5 135.
- **CALL / PUT / OTHER:** UNGOVERNED PUT 1–5 `INSUFFICIENT_POWER (n=45)`; 11–20 `INSUFFICIENT_POWER (n=3, n=3)`; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** a governed-vs-ungoverned difference (horizon, snapshot date and regime differ; no test run); performance.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=1250`

### DISC-F20 [DISC-F-M3-7] — Entry geometry of selected contracts (structure only)
- **Measured:** medians of strike distance, spread, calendar DTE, model flat decay, VALID contracts.
- **Data:** books (geometry); BS decay at entry IV.
- **Number:** GOVERNED strike distance CALL +0.6% / PUT −1.1%, DTE 18–21, spread 14–17%, flat decay −24% / −17%. UNGOVERNED +3.6% / +3.3%, DTE 29–30, spread 12–13%, flat decay −35% / −32%.
- **n:** 2,003 (GOVERNED 171 CALL / 116 PUT; UNGOVERNED 1,141 CALL / 575 PUT).
- **CALL / PUT / OTHER:** as above; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** that one geometry monetises better; decay figures are model values.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M3 | EVIDENCE-p23_M3_monetisation.csv | N=2003`

---

## M4 — Cheapest convexity
Data sources: contract families from `options_greeks_history` (5 snapshot dates); outcomes p32 labels; selected contracts from books 20260804_114554, 20260831_010309, 20260901_082437, 20260902_232526 (geometry only); valuation BSM r = 0.039, q = 0, IV flat. 929 chain-matched theses from 4 decision sessions; surface on a stratified sample of 601 (seed 20260912). OTHER not measured.

### DISC-F21 [DISC-F-M4-1] — Candidate count by delta band
- **Measured:** per-thesis family contracts as the delta band widens.
- **Data:** chain on matched decision sessions.
- **Number:** 0.40–0.60 / 0.30–0.70 / 0.20–0.80 / 0.10–0.85: median 2 / 3 / 5 / 7; zero-candidate theses 169 / 74 / 48 / 39; expressible share 81.8% → 92.0% → 94.8% → 95.8%.
- **n:** 929.
- **CALL / PUT / OTHER:** CALL (718) median 2 → 3 → 5 → 6, zero 136 → 54 → 38 → 31; PUT (211) 3 → 5 → 8 → 10, zero 33 → 20 → 10 → 8.
- **Does not establish:** the population behind the prompt's "median one, 305 none"; the denominator here is 929 matched theses.
- `TRACE: REQ-NONE | ALG-UNMAPPED | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_candidate_counts.csv | N=929`

### DISC-F22 [DISC-F-M4-2] — Where payoff_per_dollar peaks within thesis (delta axis)
- **Measured:** per-thesis argmax |delta| of reachable-target payoff_per_dollar; within-thesis band head-to-heads.
- **Data:** chain + BSM; reachable target spot × (1 ± 1.5·σ_h); IV flat.
- **Number:** CALL argmax |delta| median 0.36 (h5), 0.34 (h10). D025_040 beats D040_060 in 65.6% of CALL h10 theses (ratio 1.062, n=212). D060_085 beats D040_060 in 13.8% (h5) and 9.9% (h10), ratios 0.892 (n=109) and 0.861 (n=213).
- **n:** CALL h5 137, h10 303.
- **CALL / PUT / OTHER:** PUT h5 `INSUFFICIENT_POWER (n=81)`, head-to-head `INSUFFICIENT_POWER (n=67)`, h10 `INSUFFICIENT_POWER (n=49)`; not presented.
- **Does not establish:** expected value; the payoff is conditional on reaching the 1.5σ_h target at the time stop with IV flat.
- `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_h2h_delta.csv,p24_M4_h2h_tenor.csv | N=574`

### DISC-F23 [DISC-F-M4-3] — Tenor axis
- **Measured:** within-thesis head-to-head H+05_15 vs H+30_45.
- **Data:** as DISC-F22; chain DTE cap of 49 truncates the h10 window.
- **Number:** H+05_15 beats H+30_45 in 81.4% of CALL h5 theses (ratio 1.248).
- **n:** 118.
- **CALL / PUT / OTHER:** CALL h10 `INSUFFICIENT_POWER (n=66–71)`; PUT h5 `INSUFFICIENT_POWER (n=75)`.
- **Does not establish:** expected value; h10 tenor is confounded by the DTE cap and monthly-only expiries.
- `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_h2h_delta.csv,p24_M4_h2h_tenor.csv | N=574`

### DISC-F24 [DISC-F-M4-4] — Selected contract against thesis best
- **Measured:** selected payoff ÷ thesis-best payoff; band offset.
- **Data:** books (selected symbol) + chain.
- **Number:** CALL in-family median ratio 0.879; band vs best: higher 92, same 48, lower 6; ≥ 90% of best 62 (42.5%). CALL h5 (n=107): in own best cell 36 (33.6%); in bucket raw-peak cell 1.
- **n:** 146.
- **CALL / PUT / OTHER:** PUT `INSUFFICIENT_POWER (n=86)`, not presented.
- **Does not establish:** that the thesis-best contract would have monetised; a model ranking on one scenario.
- `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_selected_vs_peak.csv | N=232`

### DISC-F25 [DISC-F-M4-5] — Selected geometry on book 20260804_114554
- **Measured:** side mismatch, zero delta, DTE offset.
- **Data:** book 20260804_114554 (structure) + chain; later books for comparison.
- **Number:** CALL h10: 105 of 285 symbols opposite side; `contract_delta` = 0 on 259/321; DTE offset < 5 on 212 (median 4 days); 5 expire at or before the time stop. Later books: 0 mismatches, 0 zero deltas (226 rows).
- **n:** 321.
- **CALL / PUT / OTHER:** PUT h10 `INSUFFICIENT_POWER (n=54)`, not presented.
- **Does not establish:** the intended hold; h = 10 is the p32 bucket bound.
- `TRACE: REQ-UNMAPPED | ALG-03 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_selected_geometry_by_run.csv | N=601`

### DISC-F26 [DISC-F-M4-6] — breakeven/σ_h distribution
- **Measured:** breakeven move at the time stop (V = ask + half-spread) ÷ σ_h.
- **Data:** chain + BSM + p32 σ_a.
- **Number:** CALL family-median p10/p50/p90 0.239 / 0.751 / 1.724; cheapest 0.444; selected 0.517 (n=146). PUT family-median 0.174 / 0.620 / 1.401; cheapest 0.305.
- **n:** 570 (CALL 440, PUT 130).
- **CALL / PUT / OTHER:** PUT selected `INSUFFICIENT_POWER (n=85)`.
- **Does not establish:** calibration of σ_a; the ratio falls as σ_a rises relative to IV.
- `TRACE: REQ-NONE | ALG-02,ALG-04,ALG-08 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_breakeven_summary.csv | N=570`

### DISC-F27 [DISC-F-M4-7] — breakeven/σ_h against realised outcome
- **Measured:** side_correct and TARGET_FIRST in low vs high breakeven half; Mann–Whitney; Spearman.
- **Data:** p32 outcomes + chain.
- **Number:** CALL low vs high half side_correct 62.3% vs 47.7% (220 each); TARGET_FIRST 15.9% vs 10.5%. Mann–Whitney p = 0.00019 (BH over 6 tests 0.0011; Bonferroni at 113 splits 0.021). Spearman −0.112 (p = 0.018). MFE ≥ family-median breakeven on 44.8%; terminal ≥ it on 24.8%.
- **n:** CALL 440.
- **CALL / PUT / OTHER:** PUT (n=130) halves `INSUFFICIENT_POWER (n=65, n=65)`; pooled p = 0.99.
- **Does not establish:** causality (low breakeven/σ_h co-varies with high σ_a/IV, a possible vol-regime effect); a monetisation test (MFE is intraperiod, breakeven at the time stop); anything beyond TEST-era presented-not-taken rows.
- `TRACE: REQ-NONE | ALG-02,ALG-04,ALG-08 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_breakeven_summary.csv | N=570`

### DISC-F28 [DISC-F-M4-8] — Structural vs reachable payoff
- **Measured:** structural ÷ reachable payoff_per_dollar; argmax-cell disagreement.
- **Data:** chain + BSM + book structural targets (valid only).
- **Number:** median 0.68 (CALL 0.563); argmax cell differs on 46.4% of theses.
- **n:** 235 theses (8,456 contracts).
- **CALL / PUT / OTHER:** CALL n=154; PUT `INSUFFICIENT_POWER (n=81)`, not presented.
- **Does not establish:** which target is right; divergence only.
- `TRACE: REQ-NONE | ALG-02,ALG-04 | WP-2 | STAGE-NONE | TRACK-M4 | EVIDENCE-p24_M4_summary.json | N=235`

---

## M5 — Cost of waiting and value of confirmation
Data sources: stored option chains 08-28, 08-31, 09-02, 09-03, 09-04, 09-08, 09-10 (09-01 and 09-09 absent); `phantom_history.db` (weekly); `option_contract_observations`; EXACT_OPTION_QUOTE 2026-09-11; 22 book panels (structure); p32 `label_V`. All TEST. Premium paths from the same OCC contract's stored quotes; outcomes are barrier labels, not fills.

### DISC-F29 [DISC-F-M5-1] — Early-lane IV change reproduced, with wide dispersion
- **Measured:** same-contract % IV change at selection vs an earlier stored chain.
- **Data:** 232 MONETISABLE rows of 20260905_151448 vs the 2026-08-31 chain.
- **Number:** median −1.908% (the W3.6 figure, reproduced exactly); IQR 12.4 pp (p25 −8.9 / p75 +3.5); p10 −18.4 / p90 +21.4; median −0.88 IV points.
- **n:** 148 matched of 232.
- **CALL / PUT / OTHER:** CALL `INSUFFICIENT_POWER (n=94)`; PUT `INSUFFICIENT_POWER (n=54)`; OTHER 0.
- **Does not establish:** a fair IV level; outcomes or P&L; stability across runs; a 3-trading-session change; representativeness of the unmatched contracts.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_earlylane_summary.csv | N=148`

### DISC-F30 [DISC-F-M5-2] — The W3.6 "three sessions earlier" is four trading sessions
- **Measured:** trading-session distance of the lookback; true 1-back and 2-back changes.
- **Data:** `dataset_registry` OPTION_CHAIN + NYSE calendar; `w36_iv_at_selection.py`.
- **Number:** the script counts stored-chain sessions, so 08-31 is 4 trading sessions back. True 1-back −1.12% (n=210), 2-back −2.00% (n=179); every lookback 1–5 has a median between −2.0% and +0.1%.
- **n:** 148.
- **CALL / PUT / OTHER:** not split; CALL/PUT `INSUFFICIENT_POWER (n=94, n=54)`.
- **Does not establish:** that the W3.6 conclusion changes.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-dataset_registry OPTION_CHAIN; audit/pipeline_map/AVS-IMP-FIX-001/w36_iv_at_selection.py | N=148`

### DISC-F31 [DISC-F-M5-3] — Early-lane IV change on the 10 Sep selection
- **Measured:** same-contract % IV change vs 09-04 (3 back) and 09-08 (2 back).
- **Data:** MONETISABLE rows of books 20260910_150045 and 20260911_115904.
- **Number:** 3 back median +3.7% / +3.2%, IQR about 13 pp, share ≥ +20% 10.2% / 9.2%; 2 back −1.9% / −2.2%.
- **n:** 680 / 649.
- **CALL / PUT / OTHER:** CALL +5.2 / +3.9% (n 388 / 355); PUT +2.1 / +2.1% (n 292 / 294); OTHER 0.
- **Does not establish:** a systematic effect; one selection date, sign flips with the lookback, every median far below +20%, all rows share one market day.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_earlylane_summary.csv | N=1329`

### DISC-F32 [DISC-F-M5-4] — Stale contracts' own move cannot be measured
- **Measured:** stored re-quotes after the stale timestamp.
- **Data:** book 20260911_115904 + `option_contract_observations` + EXACT_OPTION_QUOTE.
- **Number:** 0 of 453 stale contracts have a quote after 2026-09-10T17Z; `morning_contract_mid` = `contract_mid` on 453/453; `contract_mid_change_pct` null on 453/453.
- **n:** 453.
- **CALL / PUT / OTHER:** 255 / 198 / 0.
- **Does not establish:** that they did not move; why they were not re-quoted.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_staleness.csv | N=453`

### DISC-F33 [DISC-F-M5-5] — Proxy: one-session mid move of same-book non-stale contracts (PARTIAL)
- **Measured:** absolute and signed Δmid between the 10 Sep and 11 Sep quotes (about 23.6 h apart).
- **Data:** same-book non-stale contracts.
- **Number:** |Δmid| median 11.8% (IQR 5.0–25.0; p10 1.7 / p90 43.3); signed median +1.0%; 11 Sep ask vs 10 Sep mid +30.2%; ΔIV −1.25 points; 25.3% moved more than the prior half-spread.
- **n:** 455.
- **CALL / PUT / OTHER:** CALL 12.1% (n=316); PUT 10.5% (n=139); OTHER 0.
- **Does not establish:** the stale contracts' own move (different mix, cheaper premiums); a direction of cost; fill at the ask.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_staleness_proxy.csv | N=455`

### DISC-F34 [DISC-F-M5-6] — Thesis identity is not stable across sessions
- **Measured:** recurrence of `thesis_id`.
- **Data:** book panel.
- **Number:** 2,887 distinct ids; 752 recur; 87% embed their own session date, so repeats use a ticker+direction cohort (PARTIAL). Contract changed on 30% / 47% / 36% / 71% of pairs at d = 1 / 2 / 3 / 5.
- **n:** 3,639 rows.
- **CALL / PUT / OTHER:** not split.
- **Does not establish:** that a cohort repeat is the same economic thesis.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_repeats.csv | N=3639`

### DISC-F35 [DISC-F-M5-7] — Holding the same contract: theta is the steadiest premium component
- **Measured:** decomposition of same-contract premium change into theta, IV, move and residual.
- **Data:** clean chain-to-chain cohort pairs, starting on 2–4 sessions (08-28 … 09-08).
- **Number:** theta in powered cells about −2 / −7 / −17 / −26% of premium at d = 1/2/3/5; IV component −0.2 to +8%. Clean totals: d1 CALL 0.0%; d3 CALL −33.9% (theta −18.8, IV +8.0, move −28.2); d3 PUT +17.4% (move +22.4).
- **n:** 769 (powered: d1 CALL 146, d3 CALL 160, d3 PUT 100).
- **CALL / PUT / OTHER:** d1 PUT `INSUFFICIENT_POWER (n=86)`; d2 CALL `(n=65)`; d2 PUT `(n=56)`; d5 CALL `(n=93)`; d5 PUT `(n=63)`; per-hidden_state and per-liquidity_state cells `INSUFFICIENT_POWER (largest n=71, n=79)`; OTHER excluded.
- **Does not establish:** a general cost of waiting (2–4 start sessions, waiting never executed, no payoff); that d3 figures are decay rather than a common move (CALL and PUT signs opposite).
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_repeats_chainonly.csv | N=769`

### DISC-F36 [DISC-F-M5-8] — delta_p is powered only on pre-20260831 state cells, and is about 0 there
- **Measured:** change in P(TARGET_FIRST | hidden_state × confirmation state) between t and t+d.
- **Data:** p32 `label_V`; hidden_state × `lab_verdict` cells.
- **Number:** 4 of 23 cells have n ≥ 100: COMPRESSED_BALANCED × `BLOCKED` 0.023 (n=389); COMPRESSED_BALANCED × MVR 0.055 (n=2,763); LOW_ENERGY_NO_EDGE × `BLOCKED` 0.029 (n=450); LOW_ENERGY_NO_EDGE × MVR 0.065 (n=6,025). Powered delta_p median 0.000 at every d; mean −0.007 / −0.009 / −0.002 / −0.012; range −0.042 to +0.036. 3 clean-repriced pairs carry a powered delta_p.
- **n:** 9,693 labelled rows; powered pairs 3,611 / 2,729 / 1,458 / 1,910.
- **CALL / PUT / OTHER:** not split; every `MANUAL_REVIEW` state cell `INSUFFICIENT_POWER (n≤88)`.
- **Does not establish:** that confirmation has no value (base rates 2–7% leave little room to detect change); anything about fills; the waiting-inequality shares (computed on contaminated pairs; not a result).
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M5 | EVIDENCE-p25_M5_state_cells.csv; p25_M5_repeats.csv | N=9693`

---

## M6 — What the gates select on
Data sources: per-run artefacts of the 22 book runs (dropoff audits, Discovery lifecycle, rejection logs, EOD dropoff audits, `garch_forecasts`). Outcomes retrospective from `ohlcv_daily` with symmetric barrier S0·(1 ± 1.5·σ·√(h/252)); agreement with p32 98.97%. Resolvable subset 15 runs, 38,478 rows. No ledger outcomes. TEST. Hit = TARGET_FIRST; OTHER uses touch-either-barrier.

### DISC-F37 [DISC-F-M6-1] — Options Intelligence scope removes CALL rows with a higher hit rate than survivors
- **Measured:** removed vs survivor hit rate, pooled; Newcombe interval; ticker bootstrap.
- **Data:** dropoff audit + `ohlcv_daily`, runs 20260723–20260902.
- **Number:** CALL removed 11.4% vs survivors 8.1%; diff −0.033 [−0.045, −0.021], bootstrap [−0.048, −0.016]; removed > survivor in 9 of 12 per-run cells.
- **n:** 20,012.
- **CALL / PUT / OTHER:** CALL survivors 14,343, removed 3,082. PUT survivors 2,452 / removed 235: 3.8% vs 3.0%, diff +0.008 [−0.023, 0.025]. OTHER touch 7.0% vs 13.3% (1,504 / 158), diff −0.063 [−0.126, −0.017].
- **Does not establish:** monetisability or P&L; survival of a σ-matched comparison (removed rows have lower σ, so a closer barrier); anything beyond retrospective TEST labels.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_gate_table.csv | N=20012`

### DISC-F38 [DISC-F-M6-2] — Pre-book EIL/EOD manifest stage removes rows with higher hit and side-correct rates
- **Measured:** removed vs survivor hit and side_correct, pooled.
- **Data:** dropoff audit + `ohlcv_daily`, runs ≤ 20260902.
- **Number:** CALL hit 9.0% vs 7.7%, diff −0.013 [−0.024, −0.003]; side_correct 50.0% vs 45.1%. PUT hit 6.3% vs 3.2%, diff −0.031 [−0.058, −0.010]; side_correct 59.2% vs 53.5%. Survivors' `oi_options_score` SMD −0.95 (CALL).
- **n:** 16,774.
- **CALL / PUT / OTHER:** CALL 3,720 removed / 10,604 kept; PUT 463 / 1,987; OTHER survivors `INSUFFICIENT_POWER (n=28)`.
- **Does not establish:** expressibility, P&L or causality; no per-run CALL cell excludes 0 (0 of 12); PUT side_correct upper bound −0.006.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_gate_table.csv | N=16774`

### DISC-F39 [DISC-F-M6-3] — The spread gate splits by direction
- **Measured:** hit rate of tickers with a SPREAD_GT_25PCT rejection vs the rest.
- **Data:** `contract_rejection_log_<run>.csv` + `ohlcv_daily`.
- **Number:** CALL 3.7% vs 8.2%, diff +0.045 [0.019, 0.061]. PUT 8.9% vs 3.3%, diff −0.057 [−0.103, −0.024]; side_correct 65.7% vs 53.6%.
- **n:** 18,278.
- **CALL / PUT / OTHER:** CALL flagged 353; PUT flagged 213; OTHER 766 vs 738, 7.2% vs 6.8%.
- **Does not establish:** whether the spread would have consumed the move; per-run PUT consistency (per-run PUT cells `INSUFFICIENT_POWER`).
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-contract_rejection_log_<run>.csv;p26_M6_gate_table.csv | N=18278`

### DISC-F40 [DISC-F-M6-4] — OI STAND_DOWN label: CALL survivors hit more; PUT stood-down rows are side-correct more often
- **Measured:** hit and side_correct for STAND_DOWN vs the rest.
- **Data:** dropoff audit `oi_verdict` + `ohlcv_daily`.
- **Number:** CALL survivors 11.1% vs 6.9%, diff +0.042 [0.031, 0.053]; interval excludes 0 in 4 of 12 runs. PUT side_correct 56.6% vs 50.5%, diff −0.061 [−0.103, −0.018]; PUT hit interval spans 0. Selection on `oi_options_score`/`priority_score` (SMD +1.4 to +1.9) and σ (+0.40).
- **n:** 17,978.
- **CALL / PUT / OTHER:** CALL 10,263 / 4,061; PUT 1,664 / 786; OTHER 7.0% vs 7.3% (1,327 / 177).
- **Does not establish:** directional information independent of σ.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-dropoff_audit_<run>.csv oi_verdict | N=17978`

### DISC-F41 [DISC-F-M6-5] — `lab_verdict` = `BLOCKED` flags CALL rows with a lower hit rate
- **Measured:** hit rate of flagged rows vs the rest.
- **Data:** final books + `ohlcv_daily`.
- **Number:** CALL 3.7% vs 8.1%, diff +0.044 [0.028, 0.056]. Selection on `options_score` (+0.74) and `priority_score` (+0.69), not `composite_score` (−0.05).
- **n:** 12,591.
- **CALL / PUT / OTHER:** CALL flagged 890; PUT 275 flagged, 1.8% vs 3.4%, interval spans 0; OTHER `INSUFFICIENT_POWER (n=28)`. Downstream gates (GO/GO_LIMIT, Morning Gate, opportunity_tier, quote_freshness, liquidity_state) all `INSUFFICIENT_POWER (≤58 survivors)`.
- **Does not establish:** anything about GO rows or runs after 20260902; most flagged rows come from 20260824.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-final_opportunity_book_<run>.csv lab_verdict | N=12591`

### DISC-F42 [DISC-F-M6-6] — GO-set inclusion is nearly uncorrelated with every unconstrained score
- **Measured:** Spearman / point-biserial between inclusion and scores (TC), no outcomes.
- **Data:** final books, 22 runs; GO inclusion constant on 18.
- **Number:** primary-run GO inclusion |ρ_s| ≤ 0.12 for all six scores; cross-run medians −0.03 to +0.16. Non-flagged set vs `priority_score`/`options_score` 0.68 on the primary run (cross-run medians 0.14 / 0.11). EIL EXECUTE* vs `eil_composite_eod` 0.43.
- **n:** 1,444 (GO set 19 rows).
- **CALL / PUT / OTHER:** GO set has 0 OTHER rows; per-direction values in `p26_M6_tc.csv`; 19-row correlations unstable.
- **Does not establish:** that any score should drive inclusion.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_tc.csv | N=1444`

### DISC-F43 [DISC-F-M6-7] — Book rank encodes verdict order, then `priority_score`
- **Measured:** rank correlation with scores within gated sets; code path.
- **Data:** final books; `contracts/lab_control.py:3033-3041`.
- **Number:** rank vs `priority_score` median ρ 0.945; vs `composite_score` 0.03, `ev3_ev_lower_bound_return` 0.01, `eil_composite_eod` −0.04. No position size (`"HUMAN DETERMINED"`).
- **n:** 22 runs (9–21 defined).
- **CALL / PUT / OTHER:** same in each direction.
- **Does not establish:** which score the rank should use; the relationship is mechanical by construction.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-contracts/lab_control.py:3033-3041;p26_M6_tc.csv | N=22 runs`

### DISC-F44 [DISC-F-M6-8] — Effective breadth is set by correlation, not row count
- **Measured:** N_eff = n / (1 + (n−1)·ρ̄) over 60 trailing sessions.
- **Data:** `ohlcv_daily`; gate populations on 22 runs.
- **Number:** ρ̄ 0.061–0.090, giving N_eff 10.7–15.2 for populations of 179–1,695 rows. Primary run: 1,572 survivors → 13.7; 994 non-flagged → 13.1.
- **n:** 22 runs; populations ≥ 179.
- **CALL / PUT / OTHER:** all directions; 19-row GO set `INSUFFICIENT_POWER (n=19)`.
- **Does not establish:** forward correlation during the hold, or option-return correlation.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_breadth.csv | N=22 runs`

### DISC-F45 [DISC-F-M6-9] — Information coefficients on resolved rows are small
- **Measured:** Spearman IC of scores against directional return in σ units, per stage.
- **Data:** book + `ohlcv_daily`; 160 cells (99 with n ≥ 100); unadjusted.
- **Number:** CALL in book |IC| ≤ 0.09 for every score; `vanguard_probability_edge` +0.08 to +0.09 at every stage; `trigger_score` −0.09 to −0.11. PUT in book `priority_score` −0.32, `options_score` −0.25.
- **n:** CALL 10,604; PUT 171–1,987.
- **CALL / PUT / OTHER:** PUT cell n=171 (123 tickers, runs 20260831–0902, 1–5 day holds only); OTHER not measured; lab GO/GO_LIMIT `INSUFFICIENT_POWER (n=15, n=20)`; opportunity_tier `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** a stable relationship; the PUT cell comes from 3 runs and one hold bucket and would need BH across 99 cells.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_ic.csv | N=10604/1987`

### DISC-F46 [DISC-F-M6-10] — The macro route removes nothing
- **Measured:** rows differentiated by the macro fields.
- **Data:** final books 20260911_115904 and 20260906.
- **Number:** `usmi_sector_alignment` NEUTRAL 1,444/1,444 (20260911) and UNAVAILABLE 264/264 (20260906); `discovery_macro_caution` NONE 1,572/1,572; 0 rows removed.
- **n:** 1,444.
- **CALL / PUT / OTHER:** 0 / 0 / 0.
- **Does not establish:** behaviour with a populated packet.
- `TRACE: REQ-UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-p26_M6_removal_counts.csv BOOK_usmi_sector_alignment | N=1444`

### DISC-F47 [DISC-F-M6-11] — Discovery-removed tickers moved more in σ units than survivors
- **Measured:** touch-either-barrier rate and median |move|/σ_h.
- **Data:** dropoff audit + `ohlcv_daily`; σ source differs by arm (removed: RV20 fallback; survivors: GARCH).
- **Number:** touch 22.3% vs 7.6%, diff −0.147 [−0.160, −0.132], bootstrap [−0.166, −0.130]; median |move|/σ_h 0.50 vs 0.42.
- **n:** 18,363 (removed 16,701; survivors 1,662).
- **CALL / PUT / OTHER:** removed rows have no direction, so CALL/PUT cannot be compared.
- **Does not establish:** directional value; the individual effect of the seven collapsed causes; freedom from a σ-estimator artefact.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M6 | EVIDENCE-dropoff_audit_<run>.csv;ohlcv_daily | N=18363`

---

## M7 — What EV is made of
Data sources: offline DOI assessments of run 20260911_115904 produced by Track C through the production DOI service (`p12_C_offline_assessments_all_contracts.csv`, 2,385 contracts / 200 families), one TEST snapshot. Forecast input is a tester substitution (`garch_forecast_vol`); as wired, production values nothing (298/298 NOT_EVALUATED_DATA_MISSING). Book fields used: bid/ask/delta/OI only. Model arithmetic only; no historical outcomes; nothing here is an edge, hit rate or realised EV. Production EV_net reproduced on 1,093/1,093 applicable rows. OTHER n = 0 (the DOI path accepts CALL/PUT only).

### DISC-F48 [DISC-F-M7-1] — Forecast-over-IV share of EV_net
- **Measured:** vol_component ÷ EV_net (finite-difference sensitivity of EV_net to σ_forecast through the vol budget × (σ_forecast − σ_IV)); share with forecast > IV.
- **Data:** offline DOI assessments, REACHABLE:LATE:BASE cell.
- **Number:** CALL median share −0.012 (p25 −1.82, p75 0.26); PUT 0.172 (p25 0.01, p75 0.30). Forecast > IV on 44.6% of CALL and 74.9% of PUT contracts.
- **n:** 1,093.
- **CALL / PUT / OTHER:** 731 / 362 / 0; family picks `INSUFFICIENT_POWER (n=70, n=54)`.
- **Does not establish:** that the forecast is right or wrong, or that forecast-over-IV earns anything; one scenario cell's sensitivity to a substituted forecast.
- `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=1093`

### DISC-F49 [DISC-F-M7-2] — EV > 0 kept when the budget uses σ = σ_IV
- **Measured:** EV-positive contracts still positive with σ_forecast := σ_IV (production function).
- **Data:** as DISC-F48.
- **Number:** EV > 0 kept CALL 654/689 (94.9%; 5 not evaluable), PUT 352/360 (97.8%). Utility > 0 kept 276/332 (83.1%) and 138/193 (71.5%). EV ≥ 0.25 kept 399/407 and 311/323.
- **n:** 1,049.
- **CALL / PUT / OTHER:** 689 / 360 / 0.
- **Does not establish:** that positive EV is robust; the reachable target still assumes a 1.5σ move is reached.
- `TRACE: REQ-NONE | ALG-01,ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=1049`

### DISC-F50 [DISC-F-M7-3] — EV rank against |delta| and premium
- **Measured:** Spearman of EV_net vs |delta| and ask; top-quintile share.
- **Data:** as DISC-F48.
- **Number:** CALL ρ −0.76 (|delta|) and −0.61 (ask); |delta| ≥ 0.60 median rank percentile 0.32 (n=467); top quintile 45.7% of low-premium tercile vs 0.4% of high. PUT ρ −0.62 / −0.39; percentile 0.24 (n=146); top quintile 30.3% vs 12.4%.
- **n:** 1,093.
- **CALL / PUT / OTHER:** 731 / 362 / 0; |delta| < 0.25 and 0.25–0.40 cells `INSUFFICIENT_POWER` (CALL n=14, 55; PUT n=12, 53).
- **Does not establish:** that low-delta or low-premium contracts perform better; one-snapshot cross-section, partly mechanical.
- `TRACE: REQ-NONE | ALG-06 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_crosstab.csv | N=1093`

### DISC-F51 [DISC-F-M7-4] — EV sign under a double-barrier probability model
- **Measured:** contracts moving from EV > 0 (reachable target treated as reached) to EV ≤ 0 under a double-barrier daily-step Monte Carlo (20,000 paths, seed 20260912, σ = row forecast), thesis vs zero drift, structural vs reachable barrier.
- **Data:** as DISC-F48; 167 of 200 families usable.
- **Number:** structural/thesis CALL 295/731 (40.4%), PUT 270/362 (74.6%); structural/zero CALL 574 (78.5%), PUT 352 (97.2%); reachable/thesis CALL 222, PUT 22; reachable/zero CALL 674, PUT 353. Every flip is positive → non-positive.
- **n:** 1,093 contracts; families CALL 101, PUT 66.
- **CALL / PUT / OTHER:** PUT family cells `INSUFFICIENT_POWER (n=66 families)`; family-pick flips `INSUFFICIENT_POWER (n=70, n=54)`; contracts share one probability triple per family; OTHER 0.
- **Does not establish:** calibrated probabilities (ALG-09 absent); GBM at the forecast σ, no jumps, LATE-cell payoffs at barrier time.
- `TRACE: REQ-NONE | ALG-02,ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_reachability_summary.csv | N=1093`

### DISC-F52 [DISC-F-M7-5] — Double-barrier p_target against single-barrier first passage
- **Measured:** median relative difference of MC p_T vs closed-form single-barrier p.
- **Data:** as DISC-F51; correctness check closed form vs single-barrier MC max abs difference ≤ 0.011.
- **Number:** CALL structural −19.0% (thesis) / −32.1% (zero); CALL reachable −10.7% / −11.6%.
- **n:** 101 CALL families.
- **CALL / PUT / OTHER:** PUT `INSUFFICIENT_POWER (n=66 families)`; OTHER 0.
- **Does not establish:** calibrated probabilities (model as DISC-F51).
- `TRACE: REQ-NONE | ALG-02 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_reachability.csv | N=167`

### DISC-F53 [DISC-F-M7-6] — EV > 0 survivors under friction variants
- **Measured:** EV-positive counts under configured friction (cap 0.15, domain 0.30), domain lifted, full half-spread.
- **Data:** as DISC-F48.
- **Number:** CALL 689 / 1,025 / 837; PUT 360 / 551 / 462. Inside the domain capped = full on 1,093/1,093; outside it CALL 336 → 148, PUT 191 → 102.
- **n:** 2,385 (CALL 1,427, PUT 958).
- **CALL / PUT / OTHER:** as above; OTHER 0.
- **Does not establish:** realised friction (no fills).
- `TRACE: REQ-NONE | ALG-04 | WP-2 | STAGE-3 | TRACK-M7 | EVIDENCE-p27_M7_decomposition.out.json | N=2385`

### DISC-F54 [DISC-F-M7-7] — Quoted spread by |delta| and open interest
- **Measured:** s = (ask − bid)/mid; median and share with s > 0.30.
- **Data:** 11 Sep book (structure) + offline sample. 11 Sep `spread_pct` = 100·s (1,218/1,218); 10 Sep = s (1,241/1,241).
- **Number:** CALL median 0.204; 40.2% > 0.30; |delta| ≥ 0.60 0.351 (n=161); OI 0 0.478 (n=125); OI 100–999 0.143 (n=189). PUT 0.157; 32.5%; |delta| 0.40–0.60 0.139 (n=342); OI 10–99 0.159 (n=155); OI 100–999 0.131 (n=125).
- **n:** 3,642 quoted rows (book CALL 772, PUT 446).
- **CALL / PUT / OTHER:** OTHER 0 (188 unquoted). CALL `INSUFFICIENT_POWER`: |delta| < 0.25 (n=6), 0.25–0.40 (n=60), OI ≥ 1000 (n=50). PUT `INSUFFICIENT_POWER`: other delta bands (n=2, 36, 66); OI 0 (n=51), 1–9 (n=81), ≥ 1000 (n=34).
- **Does not establish:** spreads at other times (one intraday TEST snapshot).
- `TRACE: REQ-NONE | ALG-12 | WP-1 | STAGE-2 | TRACK-M7 | EVIDENCE-p27_M7_friction.csv | N=3642`

### DISC-F55 [DISC-F-M7-8] — Effective half-spread multiplier is unestimable
- **Measured:** fills available for estimation.
- **Data:** Track H ledger copy.
- **Number:** 0 `FILL_RECORDED`; the multiplier is unestimable; 1.0 is the only assumption the data supports.
- **n:** `INSUFFICIENT_POWER (n=0)`.
- **CALL / PUT / OTHER:** unestimable in each.
- **Does not establish:** that friction is 1.0× half-spread; only that nothing narrower is supportable.
- `TRACE: REQ-NONE | ALG-UNMAPPED | WP-7 | STAGE-NONE | TRACK-M7 | EVIDENCE-track_H.md | N=0`

---

## M8 — Where outcomes differ from base rate
Data sources: p32 `label_V` from 15 TEST runs (decision sessions 2026-07-22 → 2026-09-01), presented-not-taken; conditioning variables joined from books and sibling artefacts. No calibrated p_T exists, so comparison is against the empirical base rate of each direction × hold stratum. Unit: unique thesis, denominator 8,413. Multiple testing: BH over 248 tests; session-stratified CMH with BH over 222. OTHER `INSUFFICIENT_POWER (n=0)` throughout.

### DISC-F56 [DISC-F-M8-1] — Test population
- **Measured:** partitions, cells, tests, eligibility.
- **Data:** p32 + joins.
- **Number:** 14 partitions → 485 cells → 970 tests; eligible 248 (25.6%); `INSUFFICIENT_POWER` 650; missing 54; no contrast 18.
- **n:** 8,413.
- **CALL / PUT / OTHER:** eligible CALL 166, PUT 82, OTHER 0; all 11–20 cells `INSUFFICIENT_POWER (n=35 CALL, n=6 PUT)`.
- **Does not establish:** power for a 5-point difference (DISC-F66); anything for OTHER.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cells.csv | N=8413`

### DISC-F57 [DISC-F-M8-2] — Base rates move more across sessions than most conditions move within them
- **Measured:** stratum base rates and per-session range (sessions with n ≥ 30).
- **Data:** p32 labels.
- **Number:** TARGET_FIRST CALL 1–5 0.063 (n=843), 6–10 0.066 (n=6,018); PUT 1–5 0.033 (n=331), 6–10 0.034 (n=1,180). side_correct CALL 0.479 / 0.451; PUT 0.492 / 0.546. Session range CALL 6–10: TARGET_FIRST 0.024–0.151, side_correct 0.341–0.646; PUT 6–10: 0.012–0.084, 0.357–0.682.
- **n:** 8,413; 13 sessions.
- **CALL / PUT / OTHER:** CALL 11–20 `INSUFFICIENT_POWER (n=35)`; PUT 11–20 `INSUFFICIENT_POWER (n=6)`; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** why sessions differ; any condition correlated with the session inherits its session's rate.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_session_rates.csv | N=8413`

### DISC-F58 [DISC-F-M8-3] — Pooled significance overstates within-session significance
- **Measured:** survivors of pooled BH vs pooled + session-stratified CMH BH.
- **Data:** p32 + joins.
- **Number:** 80 → 48 survivors; 26 tests `SESSION_CONFOUNDED`, 8 of which had passed pooled BH.
- **n:** 248 / 222 tests.
- **CALL / PUT / OTHER:** survivors CALL 41, PUT 7, OTHER 0.
- **Does not establish:** that the 48 are independent evidence; hold windows overlap, tickers recur (45 tickers carry the 213 Utilities CALL 6–10 theses), names co-move within a session; p-values remain anti-conservative by an unmeasured factor.
- `TRACE: REQ-UNMAPPED | ALG-08,ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=248`

### DISC-F59 [DISC-F-M8-4] — Sector is the largest conditional difference, mostly in side_correct
- **Measured:** within-session MH risk difference (rd_mh) for sector levels surviving both BH steps.
- **Data:** p32; sector from `horizon_*_<run>.csv` (12 runs) and books (3 runs).
- **Number:** CALL 6–10 side_correct (same sign in 8–10 of 10 sessions): Utilities −0.281 (n=213), Real Estate −0.239 (n=303), Industrials −0.125 (n=669), Consumer Discretionary −0.124 (n=605), Health Care +0.107 (n=1,088), Materials +0.132 (n=324), Energy +0.140 (n=546), ETF +0.112 (n=188). CALL 1–5 Health Care side_correct +0.164 (n=116). CALL 6–10 TARGET_FIRST: Materials +0.065, Utilities −0.055, Real Estate −0.049, Consumer Discretionary −0.031. After BH haircut, range −0.261 to +0.208.
- **n:** 14 tests, 5,176 theses (45–233 tickers per cell).
- **CALL / PUT / OTHER:** PUT 6–10 Consumer Discretionary side_correct +0.229 (n=172); OTHER 0.
- **Does not establish:** a forward or ex-ante sector signal; a CALL's side-correct rate in a sector is essentially that sector's sign over one July–September 2026 path with 13 overlapping sessions; no out-of-sample test, option P&L or advance sector call.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=14 tests / 5,176 theses`

### DISC-F60 [DISC-F-M8-5] — Regime × sector survivors re-state sector on session subsets
- **Measured:** drift status × sector survivors.
- **Data:** book `regime_drift_status` (constant within a session) + sector.
- **Number:** 17 survivors, all CALL 6–10 (12 side_correct, 5 TARGET_FIRST); e.g. DRIFTING_BEARISH·Real Estate side_correct −0.340 (n=129); DRIFTING_BULLISH·Utilities side_correct −0.311 (n=120); DRIFTING_BULLISH·Materials TARGET_FIRST +0.143 (n=156). Same sign in 4/4 or 5/5 sessions (one case 4/5).
- **n:** 17 tests.
- **CALL / PUT / OTHER:** 17 / 0 / 0.
- **Does not establish:** a regime interaction; each cell is the sector contrast on the 4–5 sessions with that label.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=17 tests`

### DISC-F61 [DISC-F-M8-6] — Regime labels cannot be separated from the session
- **Measured:** CMH status of the regime tests.
- **Data:** book `macro_regime` (TRANSITIONAL on 14 of 15 runs) and `regime_drift_status`, one value per run.
- **Number:** all 26 eligible regime tests `SESSION_CONFOUNDED`, including the largest pooled TARGET_FIRST difference in the track (DRIFTING_NEUTRAL CALL 6–10, one session, 2026-07-22).
- **n:** 26 tests.
- **CALL / PUT / OTHER:** all confounded, including PUT 6–10 NEUTRAL side_correct (n=126, one session); OTHER 0.
- **Does not establish:** anything about regime, for or against; with 13 sessions and 4 labels the question cannot be asked.
- `TRACE: REQ-UNMAPPED | ALG-13 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=26 tests`

### DISC-F62 [DISC-F-M8-7] — Compression and hidden_state split with opposite signs for CALL and PUT
- **Measured:** side_correct rd_mh for compression and hidden_state survivors.
- **Data:** p32 `hidden_state`, `compression_bucket`.
- **Number:** CALL 6–10: HIGH −0.075 (n=1,449); COMPRESSED_BALANCED −0.072 (n=1,949); LOW +0.063 (n=2,519). PUT 6–10: HIGH +0.157 (n=266); COMPRESSED_BALANCED +0.142 (n=349); LOW −0.081 (n=528). No TARGET_FIRST survivor.
- **n:** 8 tests (4 complements).
- **CALL / PUT / OTHER:** as above; OTHER 0.
- **Does not establish:** direction information in compression; opposite signs fit a common drift of compressed names, and the hidden_state pairs count one contrast twice.
- `TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=8 tests`

### DISC-F63 [DISC-F-M8-8] — Confirmation state
- **Measured:** rd_mh for `trigger_primary`, `thesis_state`, `morning_execution_permission`.
- **Data:** book; `morning_candidates_<run>`.
- **Number:** CALL 6–10 VOL_COMPRESSION side_correct −0.097, TARGET_FIRST −0.034 (n=945); NONE_OR_NULL side_correct +0.053, TARGET_FIRST +0.023 (n=4,421); TRIGGER_PENDING TARGET_FIRST +0.052 (n=318); `REPAIR_AT_OPEN` TARGET_FIRST −0.040 within session and −0.003 pooled (n=5,600; 83% of theses); `morning_execution_permission` 2 pooled survivors, 0 after stratification.
- **n:** 7 tests.
- **CALL / PUT / OTHER:** PUT 6–10 VOL_COMPRESSION side_correct +0.126 (n=155); OTHER 0.
- **Does not establish:** that confirmation buys target-first; `thesis_state` is a pre-open classification; TRIGGER_PENDING Bonferroni haircut 0.47.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=7 tests`

### DISC-F64 [DISC-F-M8-9] — IV percentile
- **Measured:** survivors on `iv_rank` terciles; the mass at 100.
- **Data:** `morning_candidates_<run>` `iv_rank`.
- **Number:** five pooled survivors, including AT_CAP_100 CALL 6–10 TARGET_FIRST +0.027 (n=2,039), drop under stratification. Two survive: CALL 6–10 T1_LOW TARGET_FIRST −0.018 (n=1,313) and PUT 6–10 T3_HIGH side_correct −0.091 (n=260); neither survives Bonferroni. 33.6% of theses have `iv_rank` = 100.0.
- **n:** 7 tests.
- **CALL / PUT / OTHER:** as above; OTHER 0.
- **Does not establish:** an IV-rank effect; the pooled difference is between-session, the target scales with σ_a, and the 100 mass may be a cap or default.
- `TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=7 tests`

### DISC-F65 [DISC-F-M8-10] — Delta band, DTE band, catalyst presence, phase: no survivor
- **Measured:** eligibility and survivors for these four variables.
- **Data:** book, morning artefacts, p32.
- **Number:** delta/DTE are 0.0 / 30.0 on 73% of theses (treated as missing), leaving 24 eligible tests and 0 survivors; catalyst PRESENT `INSUFFICIENT_POWER (n=46)`; phase has one eligible cell (CALL 1–5 C, n=129).
- **n:** 8,413.
- **CALL / PUT / OTHER:** 0 survivors in each.
- **Does not establish:** that these variables carry no information.
- `TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cells.csv | N=8413`

### DISC-F66 [DISC-F-M8-11] — Sample size required
- **Measured:** n per cell for ±5 points at 80% power.
- **Data:** stratum base rates.
- **Number:** TARGET_FIRST CALL 131–229 (α 0.05) / 398–568 (α 0.05/248); PUT 137–139 / 324–329. side_correct CALL 771–784 / 2,048–2,074; PUT 772–784 / 2,050–2,075. 11–20 strata need ≥ 347 (TARGET_FIRST) and ≥ 690 (side_correct). 13 sessions bound any session-level condition.
- **n:** 6 strata.
- **CALL / PUT / OTHER:** 11–20 strata hold `INSUFFICIENT_POWER (n=35, n=6)`; OTHER `INSUFFICIENT_POWER (n=0)`.
- **Does not establish:** the effect sizes that exist.
- `TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_power.csv | N=6 strata`

---

## M9 — Data efficiency (field census)
Data sources: all tabular artefacts of primary run 20260911_115904 (TEST, `MORNING_VALIDATION`, 00baa2b-dirty); 92 artefacts; `packages/` and `validation_events/` families on one representative each; production python corpus of 554 files. Outcome relation not testable. No entry is direction-split.

### DISC-F67 [DISC-F-M9-1] — Lab-book width against decision use
- **Measured:** Lab fields read by decision paths, under four read rules.
- **Data:** `lab_signal_book_v3.csv` (19 × 502) + corpus.
- **Number:** 502 fields; final-authority readers branch on 34 (19 in the book); the six named readers read 93 (86 logical); the broad rule gives 243.
- **n:** 502.
- **Does not establish:** that the other fields are useless (human review, dossiers, excluded coaching scripts); that no other decision path exists (dynamic reads are invisible to grep).
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_minset_decision_fields.csv | N=502`

### DISC-F68 [DISC-F-M9-2] — Constants
- **Measured:** single-valued Lab fields.
- **Data:** Lab book + 1,444-row books.
- **Number:** 200/502 (39.8%) constant; 101 constant across every 1,444-row book, 37 of them LOAD_BEARING (e.g. `quote_freshness = STALE`, `execution_authorized = False`, `convexity_score = 2.0`).
- **n:** 200.
- **Does not establish:** constancy across runs; redundancy (run-level constants serve as lineage).
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_constants_top.csv | N=200`

### DISC-F69 [DISC-F-M9-3] — Duplicate columns and alias chains
- **Measured:** byte-identical column pairs; fallback-chain call sites.
- **Data:** Lab book; `execution_gate.py`, `opportunity_tier.py`.
- **Number:** 58 fields in 41 pairs (direction ×5, contract symbol ×7, ask ×5, quote timestamp ×5, target ×4); 23 call sites form 14 alias groups.
- **n:** 58.
- **Does not establish:** semantic identity across runs or modes.
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_duplicate_pairs.csv;p22_M9_alias_chains.csv | N=58`

### DISC-F70 [DISC-F-M9-4] — All-null and unread blocks
- **Measured:** all-null fields and fields with no reader.
- **Data:** Lab book + corpus.
- **Number:** 62 all-null (`wbs_*` 15, `doi_*` 10, `underlying_nbbo_*` 8, …); 19 with no reader (11 DEAD, 8 PRODUCED_UNREAD), including the `execution_quote_*` and `validation_*` blocks.
- **n:** 62.
- **Does not establish:** that these branches never populate (WBS and DOI inactive on this run).
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_field_census.csv | N=62`

### DISC-F71 [DISC-F-M9-5] — Ambiguous units
- **Measured:** fields whose name-implied unit disagrees with the observed range.
- **Data:** all artefacts; `execution_gate.py:100–105`.
- **Number:** 848 rows (166 tokens); 15 in the Lab book, 4 of them count-field false positives. `contract_iv` spans 0.21–1.70; `*_pct` spreads hold fractions (0.085–0.178) while `contract_spread_pct_eod` holds percents (0–96.97) in the same book; `_normalise_ratio` rescales values > 1 at read time.
- **n:** 848.
- **Does not establish:** that any consumer misreads a value, or that IV > 1 is a unit mismatch.
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_ambiguous_units.csv | N=848`

### DISC-F72 [DISC-F-M9-6] — Where the unread volume sits
- **Measured:** UNREAD share by artefact.
- **Data:** all artefacts.
- **Number:** Lab book 3.8%; run-wide 40.3% (24,959/61,870); wide execution/morning books about 23%; `options_intelligence`/`execution_v3_5` 31–35%; macro JSON about 50%.
- **n:** 61,870.
- **Does not establish:** waste; the JSON payloads are lineage snapshots read by path.
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_family_classification.csv | N=61870`

### DISC-F73 [DISC-F-M9-7] — M-track instrumentation gap
- **Measured:** existence of the fields M1–M5 need.
- **Data:** all artefacts; `p20_M9_mtrack_field_map.csv`.
- **Number:** absent everywhere: forward/realised prices, realised vol over the hold, `sigma_h`, `thesis_origin_spot` (first key in `execution_gate.py:133`). Family-wide greeks and quotes exist only as `contracts_tested[].{symbol,dte,delta,spread_pct,mid}`. Packages `options_contract` 23/25 null. `contracts_tested.jsonl` `run_id` null in 1,218/1,218.
- **n:** 28 needs (25 present somewhere).
- **Does not establish:** that the measurements are impossible (forward data can be joined, `sigma_h` derived); only that run artefacts do not carry them.
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_mtrack_summary.csv | N=28`

### DISC-F74 [DISC-F-M9-8] — Producer resolution
- **Measured:** tokens never written as a python literal.
- **Data:** all artefacts + corpus.
- **Number:** 0 in the Lab book; 23,557 (38.1%) run-wide, almost all macro/provider JSON leaves (packages 8,094, interpreter 4,995, run root 3,330, core_intel 2,578); the 1,444-row CSVs have 0–17 each.
- **n:** 23,557.
- **Does not establish:** absent lineage (keys come from serialised provider objects).
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_field_census.csv | N=23557`

### DISC-F75 [DISC-F-M9-9] — Method sensitivity of "load-bearing"
- **Measured:** decision-field count under four read rules; read kinds.
- **Data:** Lab book + decision-range read sites.
- **Number:** 34 / 93 / 140 / 243 decision fields by rule (branch / fetch / anywhere in range / pass-through); 41 tokens output-only (PASS_ONLY).
- **n:** 2,056 read sites.
- **Does not establish:** which tier is correct; any headline count must name its rule.
- `TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_decision_read_kinds.csv | N=2056`

---

## Mapping — original ID → new ID

| original | new |
|---|---|
| outcome census | — (no findings stated) |
| DISC-F-M1-1 … M1-5 | DISC-F01 … DISC-F05 |
| DISC-F-M2-1 … M2-8 | DISC-F06 … DISC-F13 |
| DISC-F-M3-1 … M3-7 | DISC-F14 … DISC-F20 |
| DISC-F-M4-1 … M4-8 | DISC-F21 … DISC-F28 |
| DISC-F-M5-1 … M5-8 | DISC-F29 … DISC-F36 |
| DISC-F-M6-1 … M6-11 | DISC-F37 … DISC-F47 |
| DISC-F-M7-1 … M7-8 | DISC-F48 … DISC-F55 |
| DISC-F-M8-1 … M8-11 | DISC-F56 … DISC-F66 |
| DISC-F-M9-1 … M9-9 | DISC-F67 … DISC-F75 |

Within each track the mapping is sequential.
