# Track M8 — Where outcomes differ from base rate (DISCOVERY, §4.10)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
DISCOVERY track: it describes and measures; no verdict vocabulary, no severity. Findings are `DISC-F-M8-<n>` placeholders. Everything here is RESEARCH_ONLY; nothing authorises, sizes or clears a trade.

**Data source.** Retrospective vol-budget triple-barrier labels `label_V` (ALG-08 target S·(1 ± 1.5·σ_a·√(h/252)), row's own invalidation, daily OHLC from `db_copies/historical_prices.sqlite`) in `probes/p32_labels.csv` (9,896 rows, CALL 8,154 · PUT 1,742 · OTHER 0), from presented-not-taken candidates of 15 runs (20260723_072618 → 20260902_232526; decision sessions 2026-07-22 → 2026-09-01). Conditioning variables are joined by (run_id, ticker) from each run's `intelligence_lab/final_opportunity_book_<run>.csv`, with same-run sibling artefacts where the book lacks the column (see Deviations). **Dependency E6:** no calibrated p_T exists anywhere in the repository or stored runs; this track uses retrospective labels in its place and compares observed P(TARGET_FIRST) and P(side_correct) with the empirical stratum base rate, not with any model probability. No ledger outcome is used (the census found 0 resolved outcomes). No fills; no option monetisation.
Runs used: 15 labelled runs above (all TEST condition, pre-remediation code). The primary run 20260911_115904 and comparison 20260910_150045 contribute no labels (hold windows not elapsed).

Probes (all `audit/td/AVS-TD-001/probes/`): `p28_M8_columns.py/.csv` (column existence per run), `p28_M8_profile.py/.txt` (value profile), `p28_M8_sibling_exec.py/.csv/.txt`, `p28_M8_sibling_morning.py/.csv/.txt` (sibling coverage), `p28_M8_cells.py` → `p28_M8_joined.csv`, `p28_M8_cells.csv/.txt`, `p28_M8_bh.csv`, `p28_M8_base_rates.csv`, `p28_M8_power.csv`, `p28_M8_session_rates.csv`; `p28_M8_bh_cluster.py/.csv/.txt` (session-clustered sandwich check, discarded, see method); `p28_M8_cmh.py/.csv/.txt` (session-stratified re-test + BH); `p28_M8_robust.py/.csv/.txt` (survivor sign consistency, tickers, complements).

## Method (short)
- Unit: unique thesis = ticker × direction × decision_session; the earliest run's row is kept. 9,896 rows → 8,417 keys (1,479 rows were repeats of a thesis in a later run). Denominators exclude 3 NO_SIGMA and 1 AMBIGUOUS_TOUCH_ORDER → **8,413**.
- Outcomes: TF = `label_V == TARGET_FIRST`; SC = `side_correct` (terminal close in thesis direction).
- Stratum = direction × horizon bucket (the E6 key). Cell = stratum × one level of one conditioning variable. Base rate = stratum rate (all theses in the stratum). Difference = cell rate − base rate.
- Pooled test: two-proportion z of cell vs rest of stratum (Fisher exact where an expected count < 5); exact binomial vs base rate is also stored (`p_binom`).
- Status: `MISSING_NOT_TESTED` (missing level), `NO_CONTRAST` (level = whole stratum), `INSUFFICIENT_POWER` (n < 100, reported with n, never a result), `ELIGIBLE`.
- BH: one family over all ELIGIBLE tests × both outcomes (m = 248), q = 0.05.
- Session clustering: a sandwich-variance z clustered on decision_session was computed first (`p28_M8_bh_cluster.*`). With 10–13 clusters it is unusable (p = 1.5e-31 on a 0.15-point difference), so it is **not** used. Instead each ELIGIBLE test is re-run as a Cochran–Mantel–Haenszel test stratified by decision_session (cell vs rest *within* the same session), with a Mantel–Haenszel risk difference `rd_mh`. A level that never co-occurs with other levels in the same session is `SESSION_CONFOUNDED`. BH over the CMH-tested family (m = 222). A cell is a **survivor** only if both the pooled BH and the CMH BH give q ≤ 0.05.
- Haircut for survivors: 1 − z(adjusted p)/z(raw p), for BH and for Bonferroni (m = 222); `rd_mh_after_bh_haircut` = rd_mh × (1 − BH haircut).
- Power: n for one-sample detection of ±5 points vs the stratum base rate, 80% power, two-sided α = 0.05 and α = 0.05/248.

## Variables and operationalisation (splits)
| # | pre-registered condition | field(s) used | source | levels (theses) | missing |
|---|---|---|---|---|---|
| 1 | hidden_state | `hidden_state` | p32 labels | 6 (LOW_ENERGY_NO_EDGE 5,415 · COMPRESSED_BALANCED 2,880 · COMPRESSED_BEARISH_FORCE 78 · others ≤ 18) | 0 |
| 2 | phase | `phase` | p32 labels | A 2 · B 3 · C 211 · D 49 · E 24 | 8,128 (absent before 20260831) |
| 3 | compression bucket | `compression_bucket` (census terciles) | p32 labels | LOW 3,354 · MID 2,792 · HIGH 2,271 | 0 |
| 4 | sector | modal `sector`/`gics_sector` per ticker | `horizon/horizon_*_<run>.csv` (12 runs) + final book `gics_sector` (3 runs) | 17 labels + ETF | 0 (1,734 tickers mapped; 10 with > 1 label) |
| 5 | catalyst presence | non-STRUCTURAL `catalyst_type` OR `catalyst_event_status` present OR `earnings_date` in hold window | `morning_candidates_<run>` (+ book on 3 runs); `morning_validated_trades_<run>` | PRESENT 46 · NONE_OR_STRUCTURAL 8,371 | 0 |
| 6 | IV percentile (terciles) | `iv_rank` (0–100) | `morning_candidates_<run>` (equals book `iv_rank` on 289/289 overlapping rows) | AT_CAP_100 2,825 · T1 ≤ 38.6: 1,860 · T2 ≤ 59.3: 1,854 · T3 < 100: 1,853 | 25 |
| 7 | delta band | abs(`contract_delta`) → book `delta_band` edges (matches book band on 276/276) | final book | NEAR_ATM 1,509 · FAR_OTM 412 · DEVELOPING_OTM 313 · ITM 23 | 6,160 (delta = 0.0) |
| 8 | DTE band | `dte` (`contract_dte` absent) | final book | ≤7 260 · 8–14 186 · 15–21 575 · 22–35 1,148 · 36–60 99 | 6,149 (null or 0.0-delta with dte 30) |
| 9a | regime label | `macro_regime` | final book | TRANSITIONAL 8,356 · TRANSITIONAL_BULLISH 61 | 0 |
| 9b | regime label | `regime_drift_status` | final book | DRIFTING_BULLISH 4,268 · DRIFTING_BEARISH 3,164 · DRIFTING_NEUTRAL 796 · STABLE 189 | 0 |
| 10a | confirmation state | `thesis_state` | `morning_candidates_<run>` | REPAIR_AT_OPEN 7,104 · TRIGGER_PENDING 1,127 · READY 133 · WATCHLIST 51 · DATA_REVIEW 2 | 0 |
| 10b | confirmation state | `trigger_primary` (null and NONE merged) | final book | NONE_OR_NULL 5,932 · VOL_COMPRESSION 1,588 · TRAP 523 · RANGE_BREAK_EARLY 273 · RANGE_BREAK 101 | 0 |
| 10c | confirmation state | `morning_execution_permission` | final book (2 runs only) | NOT_ELIGIBLE 628 · NO_GO_ECONOMICS 76 · GO_LIMIT 42 · 4 more ≤ 10 | 7,650 |
| 11 | regime × sector | `regime_drift_status` + sector | as 9b, 4 | 61 | 0 |

**Split count:** 11 conditions pre-registered → 14 variable partitions examined (regime label as 2 fields, confirmation state as 3) → 485 cells → 970 tests (× TF, SC).

## Results table
| Finding ID | CALL | PUT | OTHER | data source | evidence (artefact, field, value) | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M8-1 test population | 166 eligible / 346 INSUFFICIENT_POWER / 26 missing / 8 no-contrast tests | 82 / 304 / 28 / 10 | 0 rows (labels carry no OTHER) | p32 labels + joins | `p28_M8_cells.csv` `status` | 970 tests; 8,413 theses | 248 of 970 tests (25.6%) eligible; every 11–20 cell underpowered (strata n 35 and 6) |
| DISC-F-M8-2 base rates and session spread | TF 1-5 0.063 (843) · 6-10 0.066 (6,018) · 11-20 0.143 (35, INSUFFICIENT_POWER); SC 0.479 · 0.451 · 0.343 | TF 1-5 0.033 (331) · 6-10 0.034 (1,180) · 11-20 0.167 (6, INSUFFICIENT_POWER); SC 0.492 · 0.546 · 0.667 | n/a | p32 labels | `p28_M8_base_rates.csv`, `p28_M8_session_rates.csv` | 8,413; 13 sessions | per-session range (sessions n ≥ 30): CALL 6-10 TF 0.024–0.151, SC 0.341–0.646; PUT 6-10 TF 0.012–0.084, SC 0.357–0.682 |
| DISC-F-M8-3 pooled vs session-stratified survivors | pooled BH 80 → CMH+pooled BH 41 | 7 | n/a | as above | `p28_M8_bh.csv`, `p28_M8_cmh.csv` `survives_both` | m = 248 pooled / 222 CMH | 80 → 48; 26 tests SESSION_CONFOUNDED (8 of them had passed pooled BH) |
| DISC-F-M8-4 sector × side_correct / target-first | 6-10 SC: Utilities −0.281 (213), Real Estate −0.239 (303), Industrials −0.125 (669), Cons. Disc. −0.124 (605), Health Care +0.107 (1,088), Materials +0.132 (324), Energy +0.140 (546), ETF +0.112 (188); 1-5 SC Health Care +0.164 (116). 6-10 TF: Materials +0.065, Utilities −0.055, Real Estate −0.049, Cons. Disc. −0.031 | 6-10 SC Cons. Disc. +0.229 (172) | n/a | p32 labels + horizon/final-book sector | `p28_M8_cmh.csv` rd_mh; `p28_M8_robust.csv` | 14 surviving tests | rd_mh after BH haircut −0.261…+0.208; same sign in 7–10 of 10 sessions; distinct tickers 45–233 per cell |
| DISC-F-M8-5 regime × sector | 17 surviving tests, all 6-10 (12 SC, 5 TF), e.g. DRIFTING_BEARISH·Real Estate SC −0.340 (129), DRIFTING_BULLISH·Utilities SC −0.311 (120), DRIFTING_BULLISH·Materials TF +0.143 (156) | 0 | n/a | as F-M8-4 | `p28_M8_robust.csv` | 17 | same sign in 4/4 or 5/5 sessions (1 case 4/5) |
| DISC-F-M8-6 regime labels | macro_regime: 4 eligible tests, all SESSION_CONFOUNDED; drift status: all 22 SESSION_CONFOUNDED, incl. DRIFTING_NEUTRAL 6-10 TF 0.146 vs 0.066 (610, 1 session) | drift status PUT 6-10 NEUTRAL SC −0.189 (126, 1 session) | n/a | final book | `p28_M8_cmh.csv` `cmh_status` | 26 tests | not separable from session; no regime survivor |
| DISC-F-M8-7 hidden_state / compression | 6-10 SC: COMPRESSED_BALANCED −0.072 (1,949) (LOW_ENERGY is its mirror +0.072); compression HIGH −0.075 (1,449), LOW +0.063 (2,519) | 6-10 SC: COMPRESSED_BALANCED +0.142 (349) (LOW_ENERGY mirror −0.142); compression HIGH +0.157 (266), LOW −0.081 (528) | n/a | p32 labels | `p28_M8_robust.csv` | 8 tests (4 are complements) | opposite signs for CALL and PUT; no TF survivor for these variables |
| DISC-F-M8-8 confirmation state | trigger VOL_COMPRESSION 6-10 SC −0.097, TF −0.034 (945); NONE_OR_NULL SC +0.053, TF +0.023 (4,421); thesis_state TRIGGER_PENDING 6-10 TF +0.052 (318), REPAIR_AT_OPEN TF −0.040 (5,600) | trigger VOL_COMPRESSION 6-10 SC +0.126 (155) | n/a | final book / morning_candidates | `p28_M8_robust.csv` | 7 tests | morning_permission: 2 pooled survivors, 0 after CMH (1 session with contrast) |
| DISC-F-M8-9 IV percentile | T1_LOW 6-10 TF −0.018 (1,313; pooled −0.035); AT_CAP_100 and T2 pooled survivors did not survive CMH | T3_HIGH 6-10 SC −0.091 (260) | n/a | morning_candidates `iv_rank` | `p28_M8_cmh.csv` | 2 surviving tests; 5 dropped by CMH | 33.6% of theses at iv_rank 100.0 |
| DISC-F-M8-10 delta band, DTE band, catalyst, phase | 0 survivors; delta/DTE eligible only on non-default rows | 0 survivors | n/a | final book; morning artefacts | `p28_M8_cells.csv` | delta/DTE 24 eligible tests; catalyst PRESENT n = 46 → every PRESENT cell INSUFFICIENT_POWER; phase C (CALL 1-5, n 129) only eligible phase cell | 73% of theses carry delta 0.0; catalyst NONE cells ≈ whole stratum (|diff| ≤ 0.003) |
| DISC-F-M8-11 power | TF needs 131–229 per cell at α 0.05, 398–568 at α 0.05/248; SC needs 771–784, 2,048–2,074 | TF 137–139 / 324–329; SC 772–784 / 2,050–2,075 | n/a | base rates | `p28_M8_power.csv` | 6 strata | 11-20 strata need ≥ 347 (TF) and ≥ 690 (SC) vs 35 and 6 available |

## Split table (per variable; tests = cells × 2 outcomes)
| variable | cells | tests | ELIGIBLE | INSUFFICIENT_POWER | MISSING / NO_CONTRAST | pooled-BH survivors | CMH+pooled BH survivors |
|---|---|---|---|---|---|---|---|
| hidden_state | 19 | 38 | 16 | 20 | 0 / 2 | 5 | 4 |
| phase | 15 | 30 | 2 | 16 | 12 / 0 | 0 | 0 |
| compression_bucket | 17 | 34 | 20 | 14 | 0 / 0 | 5 | 4 |
| sector | 71 | 142 | 38 | 104 | 0 / 0 | 15 | 14 |
| catalyst_presence | 10 | 20 | 8 | 8 (all PRESENT cells) | 0 / 4 | 0 | 0 |
| iv_percentile | 25 | 50 | 26 | 18 | 6 / 0 | 7 | 2 |
| delta_band | 22 | 44 | 12 | 20 | 12 / 0 | 0 | 0 |
| dte_band | 18 | 36 | 12 | 12 | 12 / 0 | 1 | 0 |
| regime_macro_regime | 8 | 16 | 4 | 4 | 0 / 8 | 0 | 0 (all 4 SESSION_CONFOUNDED) |
| regime_drift_status | 20 | 40 | 22 | 18 | 0 / 0 | 8 | 0 (all 22 SESSION_CONFOUNDED) |
| confirm_thesis_state | 20 | 40 | 16 | 24 | 0 / 0 | 2 | 2 |
| confirm_trigger_primary | 20 | 40 | 20 | 16 | 0 / 4 | 8 | 5 |
| confirm_morning_permission | 23 | 46 | 2 | 32 | 12 / 0 | 2 | 0 |
| regime_drift_x_sector | 197 | 394 | 50 | 344 | 0 / 0 | 27 | 17 |
| **total** | **485** | **970** | **248** | **650** | **54 / 18** | **80** | **48** |
Source: `probes/p28_M8_split_table.py` → `p28_M8_split_table.csv`.

## BH table — the 48 survivors (pooled BH q ≤ 0.05 AND session-stratified CMH BH q ≤ 0.05)
All RESEARCH_ONLY. `diff` = pooled cell − base; `rd_mh` = within-session MH risk difference; haircuts relative to the CMH p; Bonferroni at m = 222 (a haircut of 1.00 means it does not survive Bonferroni).
| variable | stratum | level | outcome | n | rate | base | diff | rd_mh | p_raw | p_bh | p_cmh | p_cmh_bh | haircut BH | haircut Bonf | rd_mh after BH haircut | sessions same sign |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sector | CALL 6-10 | Real Estate | SC | 303 | 0.221 | 0.451 | −0.230 | −0.239 | 1.4e-16 | 1.2e-14 | 1.4e-16 | 2.1e-14 | 0.075 | 0.081 | −0.221 | 10/10 |
| sector | CALL 6-10 | Utilities | SC | 213 | 0.174 | 0.451 | −0.278 | −0.281 | 1.1e-16 | 1.2e-14 | 1.9e-16 | 2.1e-14 | 0.071 | 0.082 | −0.261 | 9/10 |
| drift×sector | CALL 6-10 | BULLISH·Health Care | SC | 539 | 0.573 | 0.451 | +0.122 | +0.184 | 2.5e-09 | 5.1e-08 | 1.4e-15 | 1.0e-13 | 0.069 | 0.087 | +0.172 | 5/5 |
| drift×sector | CALL 6-10 | BEARISH·Real Estate | SC | 129 | 0.132 | 0.451 | −0.320 | −0.340 | 1.7e-13 | 8.3e-12 | 2.3e-14 | 1.3e-12 | 0.070 | 0.096 | −0.316 | 4/4 |
| drift×sector | CALL 6-10 | BEARISH·Energy | SC | 208 | 0.692 | 0.451 | +0.241 | +0.260 | 1.2e-12 | 4.9e-11 | 3.6e-13 | 1.4e-11 | 0.071 | 0.106 | +0.241 | 4/4 |
| drift×sector | CALL 6-10 | BULLISH·Materials | TF | 156 | 0.199 | 0.066 | +0.133 | +0.143 | 1.2e-11 | 3.6e-10 | 3.8e-13 | 1.4e-11 | 0.070 | 0.106 | +0.133 | 5/5 |
| drift×sector | CALL 6-10 | BULLISH·Utilities | SC | 120 | 0.117 | 0.451 | −0.335 | −0.311 | 1.0e-13 | 6.2e-12 | 6.9e-12 | 2.2e-10 | 0.075 | 0.119 | −0.288 | 5/5 |
| sector | CALL 6-10 | Health Care | SC | 1,088 | 0.538 | 0.451 | +0.086 | +0.107 | 2.5e-10 | 7.0e-09 | 7.8e-11 | 2.2e-09 | 0.080 | 0.133 | +0.098 | 8/10 |
| sector | CALL 6-10 | Energy | SC | 546 | 0.575 | 0.451 | +0.124 | +0.140 | 1.1e-09 | 2.7e-08 | 2.0e-10 | 4.9e-09 | 0.081 | 0.140 | +0.129 | 9/10 |
| sector | CALL 6-10 | Industrials | SC | 669 | 0.344 | 0.451 | −0.108 | −0.125 | 3.1e-09 | 5.9e-08 | 5.0e-10 | 1.1e-08 | 0.081 | 0.147 | −0.115 | 8/10 |
| sector | CALL 6-10 | Consumer Discretionary | SC | 605 | 0.344 | 0.451 | −0.108 | −0.124 | 2.1e-08 | 3.1e-07 | 3.2e-09 | 6.5e-08 | 0.087 | 0.163 | −0.113 | 9/10 |
| sector | PUT 6-10 | Consumer Discretionary | SC | 172 | 0.738 | 0.546 | +0.193 | +0.229 | 4.0e-08 | 5.3e-07 | 1.6e-08 | 2.9e-07 | 0.093 | 0.179 | +0.208 | 9/10 |
| trigger_primary | CALL 6-10 | VOL_COMPRESSION | SC | 945 | 0.372 | 0.451 | −0.079 | −0.097 | 1.1e-07 | 1.1e-06 | 4.8e-08 | 8.2e-07 | 0.097 | 0.193 | −0.087 | 7/9 |
| drift×sector | CALL 6-10 | BEARISH·Cons. Disc. | SC | 209 | 0.306 | 0.451 | −0.145 | −0.187 | 1.8e-05 | 1.2e-04 | 1.5e-07 | 2.2e-06 | 0.100 | 0.210 | −0.168 | 4/4 |
| hidden_state | CALL 6-10 | COMPRESSED_BALANCED | SC | 1,949 | 0.401 | 0.451 | −0.050 | −0.072 | 6.5e-08 | 7.1e-07 | 1.7e-07 | 2.2e-06 | 0.096 | 0.211 | −0.065 | 8/10 |
| hidden_state | CALL 6-10 | LOW_ENERGY_NO_EDGE (mirror) | SC | 4,069 | 0.475 | 0.451 | +0.024 | +0.072 | 6.5e-08 | 7.1e-07 | 1.7e-07 | 2.2e-06 | 0.096 | 0.211 | +0.065 | 8/10 |
| drift×sector | CALL 6-10 | BULLISH·Energy | SC | 277 | 0.563 | 0.451 | +0.112 | +0.161 | 1.3e-04 | 7.4e-04 | 1.7e-07 | 2.2e-06 | 0.095 | 0.212 | +0.145 | 5/5 |
| compression | CALL 6-10 | HIGH | SC | 1,449 | 0.389 | 0.451 | −0.062 | −0.075 | 5.0e-08 | 6.3e-07 | 5.0e-07 | 6.2e-06 | 0.101 | 0.231 | −0.068 | 8/10 |
| drift×sector | CALL 6-10 | BULLISH·Industrials | SC | 352 | 0.301 | 0.451 | −0.150 | −0.138 | 5.4e-09 | 9.5e-08 | 5.4e-07 | 6.3e-06 | 0.099 | 0.232 | −0.125 | 4/5 |
| compression | CALL 6-10 | LOW | SC | 2,519 | 0.489 | 0.451 | +0.038 | +0.063 | 4.5e-07 | 3.9e-06 | 1.4e-06 | 1.6e-05 | 0.104 | 0.253 | +0.056 | 8/10 |
| sector | CALL 6-10 | Materials | SC | 324 | 0.577 | 0.451 | +0.126 | +0.132 | 2.9e-06 | 2.2e-05 | 2.3e-06 | 2.4e-05 | 0.107 | 0.264 | +0.118 | 9/10 |
| drift×sector | CALL 6-10 | BULLISH·Cons. Disc. | SC | 330 | 0.303 | 0.451 | −0.148 | −0.133 | 2.6e-08 | 3.6e-07 | 2.9e-06 | 2.9e-05 | 0.107 | 0.270 | −0.119 | 5/5 |
| sector | CALL 6-10 | Materials | TF | 324 | 0.127 | 0.066 | +0.061 | +0.065 | 5.8e-06 | 4.1e-05 | 3.1e-06 | 3.0e-05 | 0.105 | 0.273 | +0.058 | 8/10 |
| drift×sector | CALL 6-10 | BULLISH·Materials | SC | 156 | 0.590 | 0.451 | +0.138 | +0.182 | 4.3e-04 | 2.2e-03 | 5.3e-06 | 4.9e-05 | 0.108 | 0.287 | +0.163 | 5/5 |
| drift×sector | CALL 6-10 | BEARISH·Industrials | SC | 233 | 0.326 | 0.451 | −0.125 | −0.153 | 9.0e-05 | 5.3e-04 | 6.1e-06 | 5.4e-05 | 0.108 | 0.292 | −0.137 | 4/4 |
| drift×sector | CALL 6-10 | BULLISH·Health Care | TF | 539 | 0.108 | 0.066 | +0.042 | +0.052 | 4.1e-05 | 2.5e-04 | 6.4e-06 | 5.4e-05 | 0.106 | 0.293 | +0.046 | 4/5 |
| compression | PUT 6-10 | HIGH | SC | 266 | 0.692 | 0.546 | +0.146 | +0.157 | 5.6e-08 | 6.6e-07 | 1.1e-05 | 9.1e-05 | 0.110 | 0.311 | +0.140 | 8/10 |
| hidden_state | PUT 6-10 | COMPRESSED_BALANCED | SC | 349 | 0.662 | 0.546 | +0.116 | +0.142 | 2.1e-07 | 1.9e-06 | 1.3e-05 | 9.6e-05 | 0.107 | 0.315 | +0.126 | 9/10 |
| hidden_state | PUT 6-10 | LOW_ENERGY_NO_EDGE (mirror) | SC | 831 | 0.497 | 0.546 | −0.049 | −0.142 | 2.1e-07 | 1.9e-06 | 1.3e-05 | 9.6e-05 | 0.107 | 0.315 | −0.126 | 9/10 |
| drift×sector | CALL 6-10 | BEARISH·Info Tech | SC | 376 | 0.566 | 0.451 | +0.115 | +0.117 | 3.6e-06 | 2.6e-05 | 2.5e-05 | 1.8e-04 | 0.113 | 0.341 | +0.104 | 4/4 |
| trigger_primary | CALL 6-10 | VOL_COMPRESSION | TF | 945 | 0.040 | 0.066 | −0.026 | −0.034 | 5.5e-04 | 2.7e-03 | 1.7e-04 | 1.2e-03 | 0.140 | 0.448 | −0.029 | 8/9 |
| drift×sector | CALL 6-10 | BULLISH·Cons. Disc. | TF | 330 | 0.018 | 0.066 | −0.048 | −0.053 | 3.3e-04 | 1.8e-03 | 2.1e-04 | 1.4e-03 | 0.141 | 0.463 | −0.045 | 5/5 |
| thesis_state | CALL 6-10 | VALID_THESIS_TRIGGER_PENDING | TF | 318 | 0.113 | 0.066 | +0.047 | +0.052 | 4.6e-04 | 2.3e-03 | 2.3e-04 | 1.5e-03 | 0.140 | 0.470 | +0.045 | 7/10 |
| trigger_primary | CALL 6-10 | NONE_OR_NULL | SC | 4,421 | 0.467 | 0.451 | +0.015 | +0.053 | 7.0e-05 | 4.3e-04 | 3.5e-04 | 2.3e-03 | 0.146 | 0.505 | +0.045 | 7/9 |
| drift×sector | CALL 6-10 | BULLISH·Real Estate | SC | 139 | 0.273 | 0.451 | −0.178 | −0.149 | 2.0e-05 | 1.3e-04 | 4.2e-04 | 2.7e-03 | 0.148 | 0.525 | −0.127 | 5/5 |
| sector | CALL 6-10 | Real Estate | TF | 303 | 0.017 | 0.066 | −0.049 | −0.049 | 3.8e-04 | 2.0e-03 | 5.2e-04 | 3.2e-03 | 0.151 | 0.546 | −0.042 | 10/10 |
| sector | CALL 1-5 | Health Care | SC | 116 | 0.621 | 0.479 | +0.141 | +0.164 | 1.0e-03 | 4.7e-03 | 6.6e-04 | 4.0e-03 | 0.154 | 0.573 | +0.139 | 9/13 |
| drift×sector | CALL 6-10 | BULLISH·Industrials | TF | 352 | 0.026 | 0.066 | −0.040 | −0.046 | 1.7e-03 | 7.4e-03 | 8.7e-04 | 5.1e-03 | 0.158 | 0.609 | −0.039 | 5/5 |
| sector | CALL 6-10 | Utilities | TF | 213 | 0.009 | 0.066 | −0.056 | −0.055 | 7.2e-04 | 3.4e-03 | 9.3e-04 | 5.3e-03 | 0.158 | 0.618 | −0.047 | 10/10 |
| thesis_state | CALL 6-10 | VALID_THESIS_REPAIR_AT_OPEN | TF | 5,600 | 0.063 | 0.066 | −0.003 | −0.040 | 3.0e-03 | 1.3e-02 | 1.2e-03 | 6.4e-03 | 0.161 | 0.651 | −0.034 | 8/10 |
| sector | CALL 6-10 | ETF | SC | 188 | 0.548 | 0.451 | +0.097 | +0.112 | 6.9e-03 | 2.5e-02 | 2.1e-03 | 1.1e-02 | 0.177 | 0.761 | +0.092 | 7/10 |
| trigger_primary | CALL 6-10 | NONE_OR_NULL | TF | 4,421 | 0.072 | 0.066 | +0.006 | +0.023 | 3.1e-03 | 1.3e-02 | 2.2e-03 | 1.2e-02 | 0.177 | 0.778 | +0.019 | 8/9 |
| trigger_primary | PUT 6-10 | VOL_COMPRESSION | SC | 155 | 0.665 | 0.546 | +0.119 | +0.126 | 1.4e-03 | 6.4e-03 | 3.6e-03 | 1.9e-02 | 0.192 | 0.914 | +0.102 | 7/9 |
| sector | CALL 6-10 | Consumer Discretionary | TF | 605 | 0.041 | 0.066 | −0.024 | −0.031 | 1.0e-02 | 3.5e-02 | 4.1e-03 | 2.1e-02 | 0.194 | 0.959 | −0.025 | 9/10 |
| compression | PUT 6-10 | LOW | SC | 528 | 0.491 | 0.546 | −0.055 | −0.081 | 6.1e-04 | 2.9e-03 | 5.9e-03 | 2.7e-02 | 0.198 | 1.00 | −0.065 | 9/10 |
| iv_percentile | CALL 6-10 | T1_LOW | TF | 1,313 | 0.031 | 0.066 | −0.035 | −0.018 | 1.1e-08 | 1.8e-07 | 6.5e-03 | 2.9e-02 | 0.197 | 1.00 | −0.015 | 8/10 |
| iv_percentile | PUT 6-10 | T3_HIGH | SC | 260 | 0.458 | 0.546 | −0.088 | −0.091 | 1.2e-03 | 5.6e-03 | 8.9e-03 | 3.8e-02 | 0.207 | 1.00 | −0.072 | 7/10 |
| drift×sector | CALL 6-10 | BULLISH·Utilities | TF | 120 | 0.008 | 0.066 | −0.058 | −0.057 | 1.0e-02 | 3.5e-02 | 1.1e-02 | 4.5e-02 | 0.213 | 1.00 | −0.045 | 5/5 |

Summary: 48 survivors (CALL 41 · PUT 7 · OTHER 0; SC 34 · TF 14). Median BH haircut 0.107 (range 0.069–0.213); median Bonferroni (m = 222) haircut 0.290; 4 survivors do not survive Bonferroni at m = 222. At the full trial count of 970 tests the haircuts are larger; not recomputed per cell. 5 survivors are complements of a two-level split (both halves of the same contrast); counted once they are 45 distinct contrasts, and the 17 drift×sector survivors re-state the sector contrasts on 4–5-session subsets. Median |rd_mh| TF 0.050, SC 0.139.

## Findings
**DISC-F-M8-1 — Test population.** Measured: 14 partitions → 485 cells → 970 tests over 8,413 unique theses; 248 tests ELIGIBLE (CALL 166, PUT 82, OTHER 0), 650 INSUFFICIENT_POWER, 54 missing levels, 18 no-contrast. Every cell in the 11–20 strata (n 35 CALL, 6 PUT) is INSUFFICIENT_POWER. *Does not establish:* that the eligible cells are well powered for a 5-point difference (see F-M8-11); OTHER theses were never labelled, so nothing is known for OTHER.
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cells.csv | N=8413

**DISC-F-M8-2 — Base rates move more across sessions than most conditions move within them.** CALL 6-10 TF ranges 0.024–0.151 and SC 0.341–0.646 across 10 sessions (n ≥ 30 each); PUT 6-10 SC 0.357–0.682. *Does not establish:* why sessions differ (market path, universe composition, label construction); it shows that any condition correlated with the session gets its session's rate.
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_session_rates.csv | N=8413

**DISC-F-M8-3 — Pooled significance overstates within-session significance.** 80 pooled BH survivors fall to 48 when each test is stratified by decision session and BH-adjusted again; 26 eligible tests have no within-session contrast at all. *Does not establish:* that the 48 are independent evidence. Theses share hold windows (sessions 1–7 trading days apart with 10-session holds overlap), the same tickers recur across sessions (e.g. 45 distinct tickers carry the 213 Utilities CALL 6-10 theses), and within a session names in the same sector co-move. CMH removes between-session base-rate differences, not within-session cross-sectional correlation, so the p-values remain anti-conservative by an unmeasured factor.
TRACE: REQ-UNMAPPED | ALG-08,ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=248

**DISC-F-M8-4 — Sector is the largest conditional difference, mostly in side_correct.** CALL 6-10 SC: Utilities −0.28, Real Estate −0.24, Industrials and Consumer Discretionary −0.12, Health Care +0.11, Materials +0.13, Energy +0.14 (MH risk differences; same sign in 8–10 of 10 sessions); PUT 6-10 Consumer Discretionary SC +0.23. TF differences are smaller (−0.055 to +0.065). *Does not establish:* a forward or ex-ante sector signal. Side-correct for a CALL in a sector is essentially that sector's sign over a July–September 2026 window with 13 overlapping decision sessions, one market path. There is no out-of-sample period, no option P&L, and no sector call the pipeline made in advance. Sector was reconstructed per ticker from sibling artefacts (not the book on 12 runs).
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=14 tests / 5,176 theses

**DISC-F-M8-5 — Regime × sector survivors re-state sector on session subsets.** 17 survivors, all CALL 6-10; regime_drift_status is constant within a session, so each drift×sector cell is the sector contrast restricted to the 4–5 sessions carrying that drift label. *Does not establish:* a regime interaction. Between-label comparisons of the same sector (e.g. Energy BEARISH +0.26 vs BULLISH +0.16) are between-session comparisons with 4 vs 5 sessions.
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=17 tests

**DISC-F-M8-6 — Regime labels cannot be separated from the session.** `macro_regime` takes one value per run (TRANSITIONAL on 14 of 15); `regime_drift_status` is one value per run. All 26 eligible regime tests (4 macro_regime, 22 drift status) are SESSION_CONFOUNDED, including the largest pooled TF difference in the track (DRIFTING_NEUTRAL CALL 6-10 TF 0.146 vs 0.066, n = 610, a single session, 2026-07-22). *Does not establish:* anything about regime, for or against; with 13 sessions and 4 labels the question is not askable.
TRACE: REQ-UNMAPPED | ALG-13 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=26 tests

**DISC-F-M8-7 — Compression / hidden_state split with opposite signs for CALL and PUT.** HIGH compression / COMPRESSED_BALANCED: CALL 6-10 SC −0.075 / −0.072, PUT 6-10 SC +0.157 / +0.142; no TF survivor for either variable. *Does not establish:* direction information in the compression state. Opposite signs in CALL and PUT are what a common downward drift of compressed names over these windows produces, independent of thesis direction. The hidden_state pairs are complements (the same contrast counted twice).
TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=8 tests

**DISC-F-M8-8 — Confirmation state.** CALL 6-10: `trigger_primary` VOL_COMPRESSION SC −0.097, TF −0.034 (n 945; the trigger overlaps the compression state); PUT 6-10 VOL_COMPRESSION SC +0.126 (155). `thesis_state` TRIGGER_PENDING CALL 6-10 TF +0.052 (318) and REPAIR_AT_OPEN TF −0.040 within session (pooled −0.003; 83% of theses carry REPAIR_AT_OPEN). `morning_execution_permission` has 2 pooled survivors and 0 after session stratification (1 session with contrast). *Does not establish:* that confirmation "buys" target-first. The thesis_state labels are the pipeline's pre-open classification, not observed confirmation; TRIGGER_PENDING TF +0.05 is within one BH haircut of zero at the Bonferroni level (haircut 0.47).
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_robust.csv | N=7 tests

**DISC-F-M8-9 — IV percentile.** Five pooled survivors (AT_CAP_100 TF +0.027 on 2,039 CALL 6-10 theses, T2_MID) do not survive session stratification; two do: CALL 6-10 T1_LOW TF −0.018 (MH; pooled −0.035) and PUT 6-10 T3_HIGH SC −0.091; neither survives Bonferroni at m = 222. 33.6% of theses have `iv_rank` = 100.0. *Does not establish:* an IV-rank effect on outcomes. The pooled AT_CAP_100 difference is largely between-session; the vol-budget target scales with σ_a, which may correlate with IV rank mechanically; the 100.0 mass may be a cap or a default.
TRACE: REQ-UNMAPPED | ALG-08 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cmh.csv | N=7 tests

**DISC-F-M8-10 — Delta band, DTE band, catalyst presence, phase: no survivor.** Delta and DTE are 0.0 / 30.0 on 73% of theses (treated as missing), so eligible cells come from non-default rows only (24 tests); catalyst PRESENT is 46 theses, so every PRESENT cell is INSUFFICIENT_POWER and the NONE cells are ≈ the whole stratum; phase is absent before 20260831, leaving one eligible cell (CALL 1-5 phase C, n 129). *Does not establish:* that these variables carry no information; the populated sample is too small or too selected.
TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_cells.csv | N=8413

**DISC-F-M8-11 — Sample size required.** One-sample ±5 points at 80% power: TF 131–229 per cell (α 0.05) and 322–568 (α 0.05/248); SC 771–784 and 2,048–2,075. The n ≥ 100 eligibility floor is below the TF requirement at family-wise α and below the SC requirement at any α; SC survivors are those with 10–34-point differences. Session count, not thesis count, bounds any session-level condition: 13 sessions in total. *Does not establish:* the effect sizes that exist; it sizes the capture needed to see 5 points.
TRACE: REQ-UNMAPPED | ALG-09 | WP-NONE | STAGE-NONE | TRACK-M8 | EVIDENCE-p28_M8_power.csv | N=6 strata

## Deviations (observations; no severity)
- **Conditioning fields missing from the final book.** Briefed as joinable from `final_opportunity_book_<run>.csv`; found: `gics_sector`, `sector`, `iv_rank`, `delta_band`, `thesis_state` and `catalyst_type/date/event_status` exist only on 20260831_010309, 20260901_082437 and 20260902_232526 (3 of 15 labelled runs); `usmi_sector_alignment`, `iv_percentile` and `contract_dte` are absent from every book; `catalyst_overlay` is present and null on all rows of all 15. This track took sector from `horizon/horizon_*_<run>.csv`, IV rank / thesis_state / catalyst fields from `morning_validation/morning_candidates_<run>.csv`, and earnings_date from `morning_validated_trades_<run>.csv`, all joined by (run_id, ticker). Evidence: `p28_M8_columns.csv`, `p28_M8_sibling_*.txt`.
- **Zero-as-missing contract geometry.** `contract_delta` = 0.0 on 73.2% of theses, and `dte` = 30.0 on 99.8% of those; `dte` = 30.0 never occurs with a non-zero delta. On the 12 pre-0831 books, 62–78% of rows per run. Evidence: `p28_M8_cells.txt` line "contract_delta==0 or null share".
- **IV rank mass at 100.** `iv_rank` = 100.0 on 33.6% of theses (18–58% per run); `iv_percentile` in execution artefacts = iv_rank/100. Evidence: `p28_M8_sibling_exec.txt`.
- **earnings_date column** is present on `morning_validated_trades` for 7 runs but 0% populated on labelled tickers. Evidence: `p28_M8_cells.txt`.
- **Regime label granularity.** `macro_regime` is one value per run and TRANSITIONAL on 14 of 15; `regime_drift_status` is also one value per run. Regime × sector therefore used `regime_drift_status`.
- **Sector vocabulary.** 10 tickers carry more than one sector label across artefacts; `ETF` appears as a sector value.
- **Unique-thesis count.** The key ticker × direction × decision_session gives 8,417 keys in p32 (8,414 labelled plus 3 NO_SIGMA), against 8,414 in `outcome_census.md` §2 (vol-budget set) and 8,421 (full-window set).

## Premise notes (spec / measured / gap; no severity, no recommendation)
- **Spec (§4.10):** find where outcomes differ from the stratum base rate across conditioning variables. **Measured:** between-session variation of the base rate (CALL 6-10 SC 0.34–0.65) exceeds most within-session conditional differences, and every regime label is session-constant. **Gap:** 13 decision sessions versus 4 regime labels, so a session-level condition has ≤ 5 sessions per level. Thesis count (8,413) is not the binding sample for these conditions.
- **Spec:** outcome = P(TARGET_FIRST) and P(side_correct). **Measured:** 34 of 48 survivors are side_correct, concentrated in sector, with opposite CALL/PUT signs for compression. **Gap:** side_correct on overlapping windows of one market path mostly measures sector/market drift, not thesis selection. The TF differences that survive are 2–14 points.
- **Spec (E6 key):** stratum = direction × hold bucket. **Measured:** the 11–20 strata hold 35 and 6 theses; 86% sit in 6–10. **Gap:** 2 of 6 E6 strata are unusable at any split.
- **Spec (Rule 12):** n < 100 is INSUFFICIENT_POWER. **Measured:** at family-wise α with m = 248, a 5-point TF difference needs 322–568 per cell and SC needs ≈ 2,050. **Gap:** cells with 100 ≤ n < ~550 (TF) or < ~2,050 (SC) are formally eligible but underpowered for 5 points.

## Not tested / limitations
- OTHER direction: NOT TESTED; p32 labels contain no OTHER rows (the 405 OTHER presented rows were never labelled).
- Structural-barrier labels (`label_S`, 3,243 rows): not used; the track uses the vol-budget set only.
- Ticker-clustered or cross-sectionally clustered inference: not computed; the session-clustered sandwich was computed and discarded as unreliable with 10–13 clusters (`p28_M8_bh_cluster.txt`).
- Bonferroni haircuts at the full 970-test count: not computed per cell.
- `usmi_sector_alignment` / USMI routing label as the regime label: absent from every book (see Track F / M1).

## Expectation vs actual
| expectations.md M8 row | expected (E) | actual (A) | Δ |
|---|---|---|---|
| cells with n ≥ 100 | 0 | 248 eligible tests (124 cell × outcome pairs ≈ 124 cells) with n ≥ 100 and a contrast | E assumed a few hundred ledger-resolved decisions; A uses 8,413 OHLC-reconstructed theses (ledger resolved outcomes remain 0) |
| splits examined | ≈ 11 conditions × ~5 levels ≈ 60 cells | 14 partitions (11 conditions; regime ×2 fields, confirmation ×3), 485 cells, 970 tests | +3 partitions, +425 cells |
| survivors | nothing survives | 80 pooled BH; 48 after session-stratified BH (41 CALL, 7 PUT); 26 session-confounded | E missed; the survivors are largely sector/session structure on one market path (F-M8-3…7) |

splits examined: 14 (pre-registered 11 conditioning variables; 485 cells; 970 tests; BH family 248 pooled / 222 session-stratified)

## State log lines
```
4.10-M8-columns,MEASURED,15,30s,"conditioning columns per final book: sector/iv_rank/thesis_state/delta_band on 3 of 15 runs; usmi_sector_alignment/iv_percentile/contract_dte absent on all; catalyst_overlay null on all"
4.10-M8-sibling-join,MEASURED,8417,300s,"sector from horizon_* (1734 tickers), iv_rank/thesis_state/catalyst from morning_candidates (fill 0.99-1.00); earnings_date 0% filled; contract_delta 0.0 on 73.2% with dte 30"
4.10-M8-cells,MEASURED,8413,120s,"unique theses 8417 (1479 repeats collapsed), denominators 8413; 14 partitions, 485 cells, 970 tests; ELIGIBLE 248 (CALL 166 PUT 82 OTHER 0); INSUFFICIENT_POWER 650; pooled BH q<=0.05 survivors 80"
4.10-M8-cmh,MEASURED,248,60s,"session-stratified CMH: 222 tested, 26 SESSION_CONFOUNDED (all regime); survivors of pooled BH and CMH BH 48 (CALL 41 PUT 7; SC 34 TF 14); median BH haircut 0.107, Bonferroni(222) 0.290; RESEARCH_ONLY"
4.10-M8-power,MEASURED,6,1s,"n for +/-5pt at 80% power: TF 131-229 (alpha .05) / 322-568 (alpha .05/248); SC 771-784 / 2048-2075; 11-20 strata n 35 and 6"
```
