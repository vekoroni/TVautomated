# Track M2 — Forecast vs implied volatility (DISCOVERY, RESEARCH_ONLY)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
This is a discovery track: no verdict vocabulary and no severity. Findings are `DISC-F-M2-<n>` placeholders for coordinator renumbering. Any cell with n < 100 is `INSUFFICIENT_POWER`. Nothing here authorises a trade.

**Data source (Rule 10).** Outcomes come only from historical prices: `db_copies/historical_prices.sqlite` `ohlcv_daily` (`POLYGON_SPLIT_ADJUSTED`, 3,048 tickers, 2026-07-01 → 2026-09-10; bars strictly after the forecast session). Forecasts: `data/output/runs/<run>/qomega/garch_forecasts_<run>.csv` on 22 runs 2026-07-23 → 2026-09-11 (`l3_forward_realised_vol` = σ_f, annual fraction). IV: `db_copies/phantom_history.db` `iv_surface_history` (weekly), `options_greeks_history` (900-ticker subsample), `db_copies/iv_history_cache.db` `iv_history`, and the IV the pipeline itself used (σ_f + `l3_iv_tailwind_score`). Buckets: `intelligence_lab/final_opportunity_book_<run>.csv` via usecols (`hidden_state_label`, `phase`, `governed_direction` else `direction`). Stored books are used for bucket labels and for field structure only.
**Dependency C9 is unmet.** No volatility validation report exists. `tools/validate_forecast_vol.py` (commit 9e9604c) takes an input and an output path, default `--minimum-n 200`, but no output of it was found under `data/`, `audit/` or `docs/`. `config/governed_constants_v1.json:13-15` carries `bias_multiplier 1.0`, `bias_multiplier_approved false`, `validation_state "UNVALIDATED"`. The ALG-10 diagnostics below are derived here, independently.

Probes (all in `audit/td/AVS-TD-001/probes/`): `p22_M2_build_panel.py` → `p22_M2_panel.csv` (+ `_log.txt`); `p22_M2_greeks_iv.py` → `p22_M2_greeks_iv.csv`; `p22_M2_analysis.py` → `p22_M2_regressions.csv`, `p22_M2_alg10.csv`, `p22_M2_stability.csv`, `p22_M2_state_correction.csv`, `p22_M2_gapfields.csv`, `p22_M2_analysis_stdout2.txt`; `p22_M2_robustness.py` → `p22_M2_robustness.csv`, `_stdout.txt`.

## Headline — (c) |ln(S_{d+h}/S_d)| ~ F_h + IV_h, coefficient on F_h (RESEARCH_ONLY)
F_h = σ_f·√(h/252); IV_h = ATM IV·√(h/252). Primary IV = `iv_surface_history` `atm_iv`, mean of call and put, latest quote_date ≤ forecast session within 5 sessions; bucket `0_7` for h=5 and `8_30` for h=10 and h=20. The panel is deduplicated to one row per (ticker, forecast session), keeping the latest run. SEs are HC1, CR1 clustered by session (t with G−1 df) and CR1 clustered by ticker.

| h | dir | n | n non-overlap | G sessions | b_F | SE HC1 | t HC1 | p HC1 | SE cl-session | t cl-session | p cl-session | t cl-ticker | b_IV | t_IV HC1 | R² (c) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | POOLED | 2,389 | 1,300 | 6 | 0.192 | 0.051 | 3.76 | 0.0002 | 0.071 | 2.72 | 0.042 | 3.51 | 0.486 | 8.88 | 0.247 |
| 5 | CALL | 724 | 599 | 6 | 0.353 | 0.104 | 3.40 | 0.0007 | 0.099 | 3.55 | 0.016 | 3.41 | 0.390 | 4.27 | 0.277 |
| 5 | PUT | 253 | 199 | 6 | 0.128 | 0.169 | 0.76 | 0.449 | 0.205 | 0.62 | 0.561 | 0.76 | 0.633 | 2.91 | 0.215 |
| 5 | OTHER | 1,412 | 798 | 6 | 0.136 | 0.059 | 2.32 | 0.020 | 0.075 | 1.83 | 0.127 | 1.81 | 0.497 | 6.97 | 0.231 |
| 10 | POOLED | 2,935 | 1,835 | 3 | 0.313 | 0.050 | 6.21 | <1e-4 | 0.033 | 9.60 | 0.011 | 5.83 | 0.181 | 4.37 | 0.171 |
| 10 | CALL | 1,745 | 1,289 | 3 | 0.331 | 0.074 | 4.45 | <1e-4 | 0.103 | 3.22 | 0.084 | 4.30 | 0.155 | 2.84 | 0.171 |
| 10 | PUT | 272 | 242 | 3 | 0.039 | 0.092 | 0.42 | 0.672 | 0.124 | 0.31 | 0.784 | 0.40 | 0.381 | 3.26 | 0.119 |
| 10 | OTHER | 918 | 738 | 3 | 0.333 | 0.072 | 4.65 | <1e-4 | 0.063 | 5.28 | 0.034 | 4.15 | 0.200 | 2.72 | 0.186 |
| 20 | POOLED | 2,931 | 1,506 | 3 | 0.196 | 0.042 | 4.72 | <1e-4 | 0.026 | 7.65 | 0.017 | 4.07 | 0.206 | 5.41 | 0.132 |
| 20 | CALL | 1,743 | 1,186 | 3 | 0.262 | 0.058 | 4.49 | <1e-4 | 0.053 | 4.96 | 0.038 | 4.25 | 0.174 | 3.52 | 0.154 |
| 20 | PUT | 270 | 234 | 3 | −0.016 | 0.115 | −0.14 | 0.892 | 0.133 | −0.12 | 0.918 | −0.13 | 0.393 | 3.73 | 0.099 |
| 20 | OTHER | 918 | 700 | 3 | 0.135 | 0.055 | 2.46 | 0.014 | 0.118 | 1.14 | 0.371 | 2.20 | 0.221 | 3.74 | 0.107 |

OTHER = STRANGLE + UNRESOLVED + tickers with a forecast but no book row. In the regression samples it is dominated by not-in-book rows (dedup panel: NOT_IN_BOOK 9,894, STRANGLE 308, UNRESOLVED 97).

**Reading.** On the primary IV proxy the pooled forecast coefficient is positive with |t| > 2 at every h, under all three SE choices; the same holds for CALL. On PUT it has |t| < 1 at every h. The result is fragile to how IV is measured (robustness below):
- **Averaged IV** (mean of ≥ 2 of surface, cache and pipeline IV): at h=5, b_F = 0.076, t = 1.57. At h=10 it is 0.273 (t 5.47) and at h=20 0.197 (t 4.19).
- **Greeks-chain ATM IV** at the expiry nearest h: at h=20, b_F = 0.021, t = 0.25.
- **Run-time book `atm_iv`** at h=5: n = 571, t = 1.37.
- **Surface IV with lag ≤ 1 session** at h=5: b_F = 0.110, t = 1.97.

Effective n is smaller than the row count, because consecutive runs produce overlapping forward windows. Per-ticker greedy non-overlap gives 1,300 / 1,835 / 1,506 pooled rows, and re-estimation on those rows gives t_F = 2.07 / 4.44 / 3.83. Session clusters are only 3–6 for the surface source, so the clustered p-values rest on very few clusters.

## Results table
| Finding ID | CALL | PUT | OTHER | data source | evidence | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M2-1 (c) forecast coef given IV, surface IV | b_F 0.353 / 0.331 / 0.262 (t_HC1 3.40 / 4.45 / 4.49) h=5/10/20 | b_F 0.128 / 0.039 / −0.016 (t 0.76 / 0.42 / −0.14) | b_F 0.136 / 0.333 / 0.135 (t 2.32 / 4.65 / 2.46) | ohlcv_daily + iv_surface_history + garch_forecasts | `p22_M2_regressions.csv` model c, y abs, iv surf | pooled 2,389 / 2,935 / 2,931; PUT 253 / 272 / 270 | pooled b_F 0.192 / 0.313 / 0.196 vs b_IV 0.486 / 0.181 / 0.206 |
| DISC-F-M2-2 (a) vs (b) R² | h5 a 0.240 b 0.254; h10 0.161 / 0.137; h20 0.140 / 0.130 | h5 0.135 / 0.208; h10 0.071 / 0.119; h20 0.049 / 0.099 | h5 0.163 / 0.225; h10 0.175 / 0.155; h20 0.089 / 0.100 | same, common surface sample | `p22_M2_regressions.csv` models a, b | as row 1 | pooled R² a / b: 0.183 / 0.238 (h5), 0.159 / 0.140 (h10), 0.115 / 0.118 (h20) |
| DISC-F-M2-3 ALG-10 level (RV_h/σ_f) | median 0.704 / 0.720 / 0.794; cov_1σ 0.792 / 0.826 / 0.790 | 0.677 / 0.705 / 0.845; cov 0.810 / 0.826 / 0.729 | 0.695 / 0.724 / 0.796; cov 0.818 / 0.806 / 0.783 | ohlcv_daily + garch_forecasts | `p22_M2_alg10.csv` | CALL 9,106 / 8,831 / 3,255; PUT 1,837 / 1,567 / 495; OTHER 6,332 / 3,062 / 1,422 | overall median 0.697 / 0.719 / 0.800; coverage 0.803 / 0.822 / 0.782 vs 0.68 nominal |
| DISC-F-M2-4 σ_f above IV | book `atm_iv` rows not split (pooled below) | — | — | iv_surface_history, iv_history, greeks, book atm_iv, pipeline IV | `p22_M2_gapfields.csv`, `p22_M2_analysis_stdout2.txt` | 1,893–14,279 per source | median σ_f/IV: surface 0_7 1.254, surface 8_30 1.146, cache 1.156, greeks 1.08–1.10, book atm_iv 1.138 (72% > 1), pipeline IV 1.118 |
| DISC-F-M2-5 ratio drift over forecast sessions | not split | not split | not split | ohlcv_daily + garch_forecasts | `p22_M2_stability.csv` | 13 / 10 / 4 sessions, each n ≥ 1,248 | median σ_f/RV h=5 ranges 1.126 → 1.747 (sd 0.19); coverage 0.586 → 0.932 |
| DISC-F-M2-6 per-hidden-state multiplier, time-ordered | — | — | — | ohlcv_daily + garch_forecasts + book hidden_state | `p22_M2_state_correction.csv` | train 6,087 / test 4,891 (h=5) | test median ratio: overall m 0.818, per-state m 0.812; median \|log ratio\| 0.315 vs 0.320 |
| DISC-F-M2-7 `_6_10d < _1_5d` | 1.000 | 1.000 | 1.000 | garch_forecasts | `p22_M2_analysis_stdout2.txt` | 13,216 / 3,491 / 13,218 (all 29,925) | ratio 6_10/1_5 = 0.4142 (range 0.4111–0.4176, rounding) |
| DISC-F-M2-8 pipeline gap fields | — | — | — | books ≥ 20260831, garch_forecasts, source | `p22_M2_gapfields.csv` | 4,759 book rows | `garch_iv_tailwind_score` median −0.0445; equals book atm_iv − σ_f within 0.01 on 33.5% (n 4,350) |

## Regression tables — (a) y ~ F, (b) y ~ IV, pooled, y = |log return| (`p22_M2_regressions.csv`)
mean(F)/mean(y) is a ratio of means. For an unbiased normal forecast the expected value of F/|r| is 1/√(2/π) = 1.253, not 1.
| h | IV source | n | R² (a) F | R² (b) IV | mean F / mean y | mean IV / mean y | median σ_f / IV |
|---|---|---|---|---|---|---|---|
| 5 | none (full panel) | 17,275 | 0.151 | — | 1.607 | — | — |
| 5 | surface 0_7 | 2,389 | 0.183 | 0.238 | 1.530 | 1.434 | 1.134 |
| 5 | pipeline IV | 8,062 | 0.143 | 0.092 | 1.582 | 1.616 | 1.085 |
| 5 | cache | 6,005 | 0.121 | 0.154 | 1.702 | 1.581 | 1.130 |
| 5 | book atm_iv | 571 | 0.119 | 0.155 | 1.818 | 1.716 | 1.146 |
| 5 | greeks | 1,618 | 0.168 | 0.171 | 1.518 | 1.482 | 1.074 |
| 10 | none | 13,460 | 0.171 | — | 1.669 | — | — |
| 10 | surface 8_30 | 2,935 | 0.159 | 0.140 | 1.597 | 1.746 | 0.940 |
| 10 | pipeline IV | 5,156 | 0.187 | 0.084 | 1.612 | 1.763 | 1.024 |
| 10 | cache | 2,216 | 0.185 | 0.243 | 1.602 | 1.568 | 1.046 |
| 10 | greeks | 824 | 0.141 | 0.145 | 1.471 | 1.637 | 0.914 |
| 20 | none | 5,172 | 0.106 | — | 1.588 | — | — |
| 20 | surface 8_30 | 2,931 | 0.115 | 0.118 | 1.709 | 1.868 | 0.941 |
| 20 | pipeline IV | 2,237 | 0.083 | 0.072 | 1.638 | 1.813 | 0.941 |
| 20 | cache | 1,406 | 0.097 | 0.150 | 1.587 | 1.730 | 0.926 |
| 20 | greeks | 824 | 0.104 | 0.166 | 1.557 | 1.720 | 0.913 |

Book atm_iv has no h=10/20 rows: the book IV exists only from 20260831, and those sessions have no complete 10- or 20-session window.

Full-panel (a), per direction (CALL / PUT / OTHER):
- h=5: b_F 0.554 / 0.454 / 0.492; R² 0.167 / 0.102 / 0.146; n 9,106 / 1,837 / 6,332.
- h=10: b_F 0.479 / 0.509 / 0.517; R² 0.175 / 0.131 / 0.182.
- h=20: b_F 0.420 / 0.472 / 0.308; R² 0.133 / 0.078 / 0.073.

### (c) across IV sources and outcome definitions, pooled (t on b_F)
| h | IV source | y | n | G sess | b_F | t HC1 | t cl-session (p) | t cl-ticker | t non-overlap | b_IV | corr(F, IV) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | surface | abs | 2,389 | 6 | 0.192 | 3.76 | 2.72 (0.042) | 3.51 | 2.07 | 0.486 | 0.745 |
| 5 | surface | RV | 2,389 | 6 | 0.228 | 6.47 | 4.05 (0.010) | 5.11 | 3.38 | 0.481 | 0.745 |
| 5 | surface | max exc | 2,389 | 6 | 0.320 | 6.44 | 3.17 (0.025) | 5.57 | 3.14 | 0.629 | 0.745 |
| 5 | pipeline | abs | 8,062 | 13 | 0.418 | 18.53 | 6.74 (<1e-4) | 12.78 | 12.68 | 0.165 | 0.548 |
| 5 | cache | abs | 6,005 | 13 | 0.191 | 4.05 | 4.12 (0.001) | 3.10 | 2.00 | 0.391 | 0.696 |
| 5 | greeks | abs | 1,618 | 6 | 0.327 | 4.67 | 4.01 (0.010) | 4.46 | 2.98 | 0.328 | 0.706 |
| 5 | book atm_iv | abs | 571 | 3 | 0.215 | 1.37 | 1.66 (0.239) | 0.96 | 0.52 | 0.407 | 0.653 |
| 10 | surface | abs | 2,935 | 3 | 0.313 | 6.21 | 9.60 (0.011) | 5.83 | 4.44 | 0.181 | 0.765 |
| 10 | pipeline | abs | 5,156 | 10 | 0.467 | 19.87 | 7.57 (<1e-4) | 14.03 | 10.68 | 0.094 | 0.510 |
| 10 | cache | abs | 2,216 | 10 | 0.175 | 2.30 | 3.30 (0.009) | 2.31 | 2.18 | 0.488 | 0.739 |
| 10 | greeks | abs | 824 | 3 | 0.250 | 2.75 | 3.66 (0.067) | 2.77 | 2.17 | 0.257 | 0.766 |
| 20 | surface | abs | 2,931 | 3 | 0.196 | 4.72 | 7.65 (0.017) | 4.07 | 3.83 | 0.206 | 0.765 |
| 20 | pipeline | abs | 2,237 | 4 | 0.219 | 7.13 | 3.87 (0.031) | 5.85 | 5.16 | 0.141 | 0.657 |
| 20 | cache | abs | 1,406 | 4 | 0.056 | 0.64 | 2.40 (0.096) | 0.64 | 0.35 | 0.408 | 0.750 |
| 20 | greeks | abs | 824 | 3 | 0.021 | 0.25 | 0.23 (0.838) | 0.21 | −0.10 | 0.457 | 0.776 |

Per-direction (c) for pipeline, cache and greeks is in `p22_M2_robustness_stdout.txt`:
- **PUT on pipeline IV:** |t| > 2 at every h (t 6.26 / 7.00 / 5.56; n 777 / 520 / 159).
- **PUT on surface and cache IV:** |t| < 2 (cache at h=10 and h=20).
- **PUT on greeks:** INSUFFICIENT_POWER at h=10 and h=20 (n 65).

### Robustness of b_F (`p22_M2_robustness.csv`)
| check | h | n | sessions | b_F | t | note |
|---|---|---|---|---|---|---|
| Fama-MacBeth, surface | 5 / 10 / 20 | 2,389 / 2,935 / 2,931 | 6 / 3 / 3 | 0.196 / 0.312 / 0.176 | 4.11 / 8.65 / 5.18 (p 0.009 / 0.013 / 0.035) | b_F > 0 in 100% of sessions; t > 2 in 33% / 100% / 67% |
| Fama-MacBeth, pipeline IV | 5 / 10 / 20 | 8,062 / 5,156 / 2,237 | 13 / 10 / 4 | 0.416 / 0.432 / 0.222 | 6.86 / 7.01 / 4.34 | b_F > 0 in all sessions |
| Fama-MacBeth, cache | 5 / 10 | 5,819 / 2,030 | 9 / 6 | 0.198 / 0.145 | 3.05 / 3.34 | t > 2 in 33% / 0% of sessions |
| surface IV, lag ≤ 1 session | 5 | 1,183 (CALL 233, PUT 125, OTHER 825) | 3 | 0.110 (CALL 0.283, PUT −0.266, OTHER 0.115) | 1.97 (2.13 / −1.36 / 1.76) | — |
| surface IV, lag ≤ 1 session | 10 | 1,246 (CALL 679, PUT 110, OTHER 457) | 1 | 0.379 (0.511 / −0.117 / 0.268) | 4.23 (3.86 / −1.23 / 2.46) | one session only |
| mean of ≥ 2 IV sources | 5 | 4,848 (CALL 923, PUT 427, OTHER 3,498) | 13 | 0.076 (0.097 / 0.165 / 0.080) | 1.57 (0.67 / 1.98 / 1.81) | — |
| mean of ≥ 2 IV sources | 10 | 2,550 (1,241 / 257 / 1,052) | 10 | 0.273 (0.336 / 0.177 / 0.213) | 5.47 (3.91 / 1.50 / 3.62) | — |
| mean of ≥ 2 IV sources | 20 | 2,123 (1,040 / 189 / 894) | 4 | 0.197 (0.266 / 0.294 / 0.106) | 4.19 (3.43 / 1.46 / 2.01) | — |

## ALG-10 diagnostics (derived here; C9 report absent) — `p22_M2_alg10.csv`
ratio = RV_h / σ_f, where RV_h = √(252/h · Σ ln(C_t/C_{t−1})²) over d+1..d+h. coverage_1σ = share of rows with |ln(C_{d+h}/C_d)| ≤ σ_f·√(h/252). Deduplicated panel; the hidden state comes from the book of the retained run.

| h | group | n | median ratio | q25 | q75 | IQR | coverage_1σ | median σ_f/RV | sessions |
|---|---|---|---|---|---|---|---|---|---|
| 5 | ALL | 17,275 | 0.697 | 0.510 | 0.930 | 0.420 | 0.803 | 1.434 | 13 |
| 5 | CALL | 9,106 | 0.704 | 0.509 | 0.944 | 0.435 | 0.792 | 1.420 | 13 |
| 5 | PUT | 1,837 | 0.677 | 0.494 | 0.916 | 0.422 | 0.810 | 1.477 | 13 |
| 5 | OTHER | 6,332 | 0.695 | 0.515 | 0.914 | 0.398 | 0.818 | 1.439 | 13 |
| 5 | COMPRESSED_BALANCED | 3,989 | 0.702 | 0.511 | 0.948 | 0.438 | 0.780 | 1.425 | 13 |
| 5 | LOW_ENERGY_NO_EDGE | 6,742 | 0.700 | 0.507 | 0.939 | 0.432 | 0.799 | 1.429 | 13 |
| 5 | COMPRESSED_BEARISH_FORCE | 108 | 0.603 | 0.463 | 0.813 | 0.350 | 0.917 | 1.660 | 3 |
| 5 | UNKNOWN (not in book) | 6,297 | 0.694 | 0.515 | 0.913 | 0.398 | 0.819 | 1.441 | 13 |
| 5 | TRENDING_BULLISH_INERTIA | 93 | INSUFFICIENT_POWER (n=93) | | | | | | 3 |
| 5 | COMPRESSED_BULLISH_FORCE | 28 | INSUFFICIENT_POWER (n=28) | | | | | | 3 |
| 5 | TRENDING_BEARISH_INERTIA | 18 | INSUFFICIENT_POWER (n=18) | | | | | | 3 |
| 5 | STRANGLE | 35 | INSUFFICIENT_POWER (n=35) | | | | | | 2 |
| 10 | ALL | 13,460 | 0.719 | 0.570 | 0.917 | 0.346 | 0.822 | 1.390 | 10 |
| 10 | CALL | 8,831 | 0.720 | 0.571 | 0.917 | 0.346 | 0.826 | 1.388 | 10 |
| 10 | PUT | 1,567 | 0.705 | 0.558 | 0.892 | 0.334 | 0.826 | 1.419 | 10 |
| 10 | OTHER | 3,062 | 0.724 | 0.573 | 0.928 | 0.355 | 0.806 | 1.382 | 10 |
| 10 | COMPRESSED_BALANCED | 3,724 | 0.724 | 0.574 | 0.905 | 0.331 | 0.816 | 1.381 | 10 |
| 10 | LOW_ENERGY_NO_EDGE | 6,674 | 0.714 | 0.568 | 0.917 | 0.349 | 0.832 | 1.400 | 10 |
| 10 | all other states, STRANGLE, UNRESOLVED | 0 | INSUFFICIENT_POWER (n=0) | | | | | | |
| 20 | ALL | 5,172 | 0.800 | 0.647 | 0.994 | 0.347 | 0.782 | 1.250 | 4 |
| 20 | CALL | 3,255 | 0.794 | 0.646 | 0.998 | 0.352 | 0.790 | 1.259 | 4 |
| 20 | PUT | 495 | 0.845 | 0.655 | 1.024 | 0.369 | 0.729 | 1.184 | 4 |
| 20 | OTHER | 1,422 | 0.796 | 0.649 | 0.982 | 0.333 | 0.783 | 1.257 | 4 |
| 20 | COMPRESSED_BALANCED | 1,124 | 0.863 | 0.700 | 1.088 | 0.387 | 0.767 | 1.159 | 4 |
| 20 | LOW_ENERGY_NO_EDGE | 2,626 | 0.776 | 0.625 | 0.961 | 0.336 | 0.788 | 1.289 | 4 |
| 20 | all other states | 0 | INSUFFICIENT_POWER (n=0) | | | | | | |

UNRESOLVED has 0 rows with a complete forward window at any h, because every UNRESOLVED direction comes from runs after 2026-09-04.

## Stability of forecast/realised over forecast sessions — `p22_M2_stability.csv`
| session | runs | n h5 | σ_f/RV h5 | cov h5 | σ_f/RV h10 | cov h10 | σ_f/RV h20 | cov h20 | median σ_f | median RV_5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-22 | 20260723_072618 | 1,375 | 1.126 | 0.586 | 1.048 | 0.686 | 1.055 | 0.713 | 0.475 | 0.399 |
| 2026-07-30 | 20260731_083130 | 1,258 | 1.322 | 0.738 | 1.281 | 0.739 | 1.314 | 0.790 | 0.524 | 0.424 |
| 2026-08-03 | 20260804_114554 | 1,253 | 1.201 | 0.718 | 1.278 | 0.772 | 1.284 | 0.786 | 0.494 | 0.411 |
| 2026-08-07 | 2 runs (latest kept) | 1,303 | 1.549 | 0.852 | 1.341 | 0.825 | 1.388 | 0.842 | 0.483 | 0.308 |
| 2026-08-13 | 20260814_114553 | 1,396 | 1.347 | 0.769 | 1.406 | 0.865 | — | — | 0.463 | 0.346 |
| 2026-08-14 | 2 runs (latest kept) | 1,408 | 1.303 | 0.739 | 1.392 | 0.817 | — | — | 0.468 | 0.350 |
| 2026-08-17 | 20260818_041214 | 1,396 | 1.336 | 0.706 | 1.405 | 0.786 | — | — | 0.467 | 0.340 |
| 2026-08-19 | 20260820_225652 | 1,403 | 1.747 | 0.925 | 1.573 | 0.894 | — | — | 0.505 | 0.280 |
| 2026-08-20 | 20260821_090928 | 1,371 | 1.704 | 0.910 | 1.542 | 0.907 | — | — | 0.483 | 0.274 |
| 2026-08-21 | 20260824_100301 | 1,307 | 1.629 | 0.932 | 1.541 | 0.920 | — | — | 0.480 | 0.285 |
| 2026-08-28 | 20260831_010309 | 1,248 | 1.560 | 0.897 | — | — | — | — | 0.477 | 0.288 |
| 2026-08-31 | 20260901_082437 | 1,283 | 1.438 | 0.848 | — | — | — | — | 0.475 | 0.323 |
| 2026-09-01 | 20260902_232526 | 1,274 | 1.438 | 0.832 | — | — | — | — | 0.477 | 0.322 |

Across sessions, the median σ_f/RV ranges:
- h=5: 1.126–1.747 (mean 1.439, sd 0.190, 13 sessions).
- h=10: 1.048–1.573 (sd 0.157, 10 sessions).
- h=20: 1.055–1.388 (sd 0.144, 4 sessions).

The median σ_f stays within 0.46–0.52, while the median realised RV_5 falls from 0.42 to 0.27. The drift therefore comes from the realised side. Every session cell has n ≥ 1,248.

## Per-hidden-state variation and a time-ordered per-state correction — `p22_M2_state_correction.csv`
Method:
- m = train median of RV/σ_f, clipped to [0.5, 1.5] (the ALG-10 form). Book rows only.
- Train = sessions before 2026-08-15; test = sessions on or after 2026-08-15.
- A state gets its own multiplier only if its train n ≥ 100. Qualifying: COMPRESSED_BALANCED (0.811 at h=5 / 0.822 at h=10) and LOW_ENERGY_NO_EDGE (0.748 / 0.756). Every other state uses the overall value.

| h | scheme | m | n test | test median ratio (after m) | test median \|log ratio\| | test coverage_1σ |
|---|---|---|---|---|---|---|
| 5 | none | 1.0 | 4,891 | 0.628 | 0.481 | 0.872 |
| 5 | overall | 0.767 | 4,891 | 0.818 | 0.315 | 0.767 |
| 5 | per-state | 0.748 / 0.811 | 4,891 | 0.812 | 0.320 | 0.772 |
| 10 | none | 1.0 | 4,320 | 0.659 | 0.429 | 0.876 |
| 10 | overall | 0.775 | 4,320 | 0.851 | 0.240 | 0.775 |
| 10 | per-state | 0.756 / 0.822 | 4,320 | 0.840 | 0.249 | 0.782 |

Per-state test cells at h=5, with the overall m:
- COMPRESSED_BALANCED: 0.816 (n 2,188).
- LOW_ENERGY_NO_EDGE: 0.818 (n 2,456).
- COMPRESSED_BEARISH_FORCE: 0.785 (n 108).
- INSUFFICIENT_POWER: TRENDING_BULLISH_INERTIA (n=93), COMPRESSED_BULLISH_FORCE (n=28), TRENDING_BEARISH_INERTIA (n=18).

Under both schemes the test median ratio stays below the ALG-10 band [0.90, 1.10], and coverage (0.767–0.782) sits above its band [0.60, 0.76].

## Pipeline-published forecast-vs-IV fields (structure only) — `p22_M2_gapfields.csv`
Book rows on runs from 20260831 onward (n = 4,759). The 12 earlier books carry only `contract_iv` of these fields.

| field | producer (file:line) | definition found | non-null | median (q25–q75) | relation measured |
|---|---|---|---|---|---|
| `garch_iv_tailwind_score` | alias of `l3_iv_tailwind_score` (`contracts/lab_control.py:2933`); computed at `layer3_forward_variance.py:531` | `implied_vol − ann_vol` if implied_vol > 0, else 0.0 | 4,759 | −0.0445 (−0.122–0.000) | equals book `atm_iv − σ_f` within 0.01 on 33.5% (n 4,350; median \|diff\| 0.018); Spearman vs (σ_f − atm_iv)/atm_iv −0.80; exactly 0 on 3.0% of book rows and on 12,141 of 29,925 forecast rows |
| IV used by Layer 3 | `garch_runner.py:172-197,329,337` | `implied_vol` or `contract_iv` from `options_intelligence_<run>.csv`, last row per ticker wins; 0.0 when absent | 17,784 non-zero of 29,925 | σ_f/IV_pipe 1.118 (0.928–1.275), n 14,279 | vs book atm_iv: Spearman 0.916, \|diff\| < 0.005 on 19.9%. vs surface IV: pipe/surf 1.072 (0_7 bucket), 1.028 (8_30) |
| `iv_vs_hv` | `scripts/avshunter_options_intelligence.py:3887,3905,3927,7067` | `atm_iv / hv_30d` (30-day historical vol, not the forecast) | 4,222 | 1.062 (0.878–1.302) | Spearman vs atm_iv/σ_f 0.73 |
| `contract_iv` | `avshunter_options_intelligence.py:3870` | median implied_vol across the chain | 4,222 | 0.438 (0.310–0.607) | contract_iv/atm_iv median 0.993; Spearman 0.905 |
| `atm_iv` | `avshunter_options_intelligence.py:3882,3901` | ATM IV, or an IV-engine proxy | 4,350 | 0.444 (0.311–0.629) | σ_f/atm_iv 1.138 (0.970–1.279); σ_f > atm_iv on 72.1% |
| `garch_forecast_vol` | book | — | 4,759 | 0.478 | identical to `l3_forward_realised_vol` on 100% (\|diff\| < 1e-4) |

No book field publishes the forecast divided by matched-tenor IV. The only forecast-vs-IV field is `garch_iv_tailwind_score`, and it is an additive difference against a contract IV that is neither ATM nor tenor-matched.

Signed return in the thesis direction (descriptive only; a non-directional vol forecast carries no sign content):

| h | CALL mean | CALL share > 0 | CALL n | PUT mean | PUT share > 0 | PUT n |
|---|---|---|---|---|---|---|
| 5 | −0.0033 | 47.4% | 9,106 | +0.0010 | 51.2% | 1,837 |
| 10 | −0.0022 | 46.0% | 8,831 | +0.0088 | 54.8% | 1,567 |
| 20 | +0.0145 | 51.0% | 3,255 | −0.0181 | 43.0% | 495 |

## Findings (what each does NOT establish)

- **DISC-F-M2-1.** With matched ATM IV from `iv_surface_history` in the regression, the Layer 3 forecast keeps a positive coefficient on realised |return|.
  - Pooled: b_F 0.192 / 0.313 / 0.196, t_HC1 3.76 / 6.21 / 4.72 at h=5/10/20.
  - CALL: same pattern.
  - PUT: not significant (t 0.76 / 0.42 / −0.14; n 253–272).
  - OTHER: mixed (t_HC1 2.32 / 4.65 / 2.46; session-clustered t 1.83 / 5.28 / 1.14).

  It does NOT establish that the forecast holds information the options market lacks, for these reasons:
  - The IV proxy is weekly and 0–5 sessions stale.
  - It is tenor-mismatched: the `8_30` bucket stands in for both h=10 and h=20.
  - Measurement error in IV shifts weight onto the correlated forecast (corr 0.75). With averaged IV at h=5, b_F falls to 0.076 (t 1.57); with greeks-chain IV at h=20 it is 0.021 (t 0.25).
  - There are only 3–6 session clusters, over 2026-07-22 → 2026-09-01.
  - Nothing here measures option P&L, edge or tradability.

  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_regressions.csv,p22_M2_robustness.csv | N=2389/2935/2931

- **DISC-F-M2-2.** Which input alone explains realised |return| better depends on horizon and IV source. On surface IV, IV alone does better at h=5 (R² 0.238 vs 0.183), worse at h=10 (0.140 vs 0.159), and about the same at h=20 (0.118 vs 0.115). On cache and greeks IV, IV does better at every h. On the pipeline's own IV, IV does worse at every h (h=5: 0.092 vs 0.143).
  It does NOT establish level calibration of either input: R² is scale-free, and the differences between sources reflect IV measurement quality as much as information.
  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_regressions.csv | N=2389/2935/2931

- **DISC-F-M2-3.** The forecast runs high against realised volatility.
  - Median RV_h/σ_f is 0.697 / 0.719 / 0.800 (IQR 0.420 / 0.346 / 0.347; n 17,275 / 13,460 / 5,172).
  - coverage_1σ is 0.803 / 0.822 / 0.782, against 0.68 nominal.
  - Read through ALG-10, the forecast is 43% / 39% / 25% too high.
  - The level is similar across CALL, PUT and OTHER (0.68–0.72 at h=5 and h=10). At h=20, PUT is 0.845 (n 495).
  - Mean F / mean |r| is 1.61 / 1.67 / 1.59, against 1.25 for an unbiased normal forecast.

  It does NOT establish a stable bias:
  - The period is 7 weeks with falling realised vol (F-M2-5).
  - Close-to-close RV omits intraday range.
  - Coverage above 0.68 partly reflects the fat-tailed distribution of |r|, not only the level.

  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_alg10.csv | N=17275/13460/5172

- **DISC-F-M2-4.** The forecast sits above market IV by 8–25% at the median, depending on IV source and tenor. Median σ_f/IV by source:
  - surface `0_7`: 1.254 (n 4,560)
  - surface `8_30`: 1.146 (n 13,919)
  - cache: 1.156 (n 13,210)
  - greeks: 1.08–1.10 (n 1,893)
  - book atm_iv: 1.138 (n 4,350)
  - pipeline IV: 1.118 (n 14,279)

  Over the same windows, IV itself sits above realised (mean IV / mean |r| 1.43–1.87).
  It does NOT establish whether the design's "20–40% gap above IV" holds for any given contract, because the proxies are ATM snapshots, not the contract priced.
  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_gapfields.csv | N=14279

- **DISC-F-M2-5.** The forecast/realised ratio is not stable across forecast sessions. At h=5 the median σ_f/RV moves from 1.126 (2026-07-22) to 1.747 (2026-08-19), sd 0.19 across 13 sessions, and coverage_1σ moves from 0.586 to 0.932. σ_f stays roughly flat (0.46–0.52) while realised RV falls (0.42 → 0.27).
  It does NOT establish a trend, a regime rule or seasonality: the sample is 13 overlapping sessions in one summer.
  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_stability.csv | N=13 sessions

- **DISC-F-M2-6.** The two populated hidden states have almost the same bias: median ratio 0.702 (COMPRESSED_BALANCED) vs 0.700 (LOW_ENERGY_NO_EDGE) at h=5, and 0.724 vs 0.714 at h=10. On a time-ordered split, a per-state multiplier does no better than the overall one:

  | h | test median, per-state m | test median, overall m | median \|log ratio\|, per-state | median \|log ratio\|, overall |
  |---|---|---|---|---|
  | 5 | 0.812 | 0.818 | 0.320 | 0.315 |
  | 10 | 0.840 | 0.851 | 0.249 | 0.240 |

  Neither scheme reaches [0.90, 1.10] on the test partition. The drift between train and test is larger than the difference between states. Four states are INSUFFICIENT_POWER (n 18–93). COMPRESSED_BEARISH_FORCE (n 108, 3 sessions) shows 0.603.
  It does NOT establish that a per-bucket correction can never help: only 2 states were testable, `phase` is absent before 20260831, and the test window is 7 sessions at h=5 and 4 at h=10.
  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_state_correction.csv | N=6087 train/4891 test

- **DISC-F-M2-7.** `l3_expected_move_6_10d < l3_expected_move_1_5d` on 100% of 29,925 forecast rows (CALL 13,216, PUT 3,491, OTHER 13,218) and in every run.
  - The ratio 6_10d / 1_5d is 0.4142 (range 0.4111–0.4176).
  - `_1_5d` equals σ_f·√(5·5/7/252)·100 (median ratio 1.000000).
  - This matches comprehension item 7: the fields are differenced in sigma space and use a 5/7 calendar conversion.

  It does NOT establish which consumers misread the field (see comprehension item 7).
  TRACE: REQ-NONE | ALG-01 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-garch_forecasts_<run>.csv | N=29925

- **DISC-F-M2-8.** The only pipeline-published forecast-vs-IV field is `garch_iv_tailwind_score` = IV − σ_f (`layer3_forward_variance.py:531`), with a book median of −0.0445.
  - Its IV input is the last-row `implied_vol` / `contract_iv` from `options_intelligence` (`garch_runner.py:190`), not the book `atm_iv`. The two agree within 0.01 on 33.5% of rows.
  - A missing IV is written as 0.0, not null (12,141 of 29,925 forecast rows).
  - `iv_vs_hv` compares IV with historical vol, not with the forecast.

  It does NOT establish how downstream scoring uses these fields.
  TRACE: REQ-NONE | ALG-10 | WP-NONE | STAGE-NONE | TRACK-M2 | EVIDENCE-p22_M2_gapfields.csv | N=4759

## Deviations (observations, no severity)
| # | claimed / expected | found | evidence |
|---|---|---|---|
| 1 | C9: a volatility validation report exists (ALG-10, AVS-VAL-001) | No report found. `tools/validate_forecast_vol.py` exists (9e9604c, 12 Sep) but has no stored output. Constants: `bias_multiplier 1.0`, `bias_multiplier_approved false`, `validation_state UNVALIDATED` | `config/governed_constants_v1.json:13-15`; find under data/, audit/, docs/ |
| 2 | `layer3_forward_variance.py:23` docstring says "positive = IV cheap vs forecast" | The code computes `implied_vol − ann_vol`, so positive means IV is expensive. The comment at `:527-529` agrees with the code, not with `:23` | `layer3_forward_variance.py:23,90,527-531` |
| 3 | Tailwind is "neutral" when IV is missing (`:452`) | A missing IV is written as 0.0, indistinguishable from IV exactly equal to the forecast; 12,141 of 29,925 forecast rows (40.6%) | `layer3_forward_variance.py:531`; `garch_runner.py:337` (`iv_map.get(t, 0.0)`) |
| 4 | `_build_iv_map` docstring: "ticker → ATM IV" | Reads `implied_vol` or `contract_iv` from every `options_intelligence` row; later rows overwrite earlier ones, so the last row per ticker wins. No ATM selection; values > 5 are treated as percent | `garch_runner.py:172-197` |
| 5 | ALG-10 uses point-in-time forecasts from baseline-eligible runs | No run is baseline-eligible. 18 of 22 runs lack `dynamic_plan.last_completed_session`, so the session was inferred as the last trading date before the run date (e.g. run 20260820_225652 maps to 2026-08-19, although the 08-20 session had already closed) | `p22_M2_build_panel_log.txt` |
| 6 | `governed_direction` available for the direction split | Absent on the 12 books before 20260831, where `direction` was used; 12,813 forecast rows have no book row | `p22_M2_build_panel_log.txt` |
| 7 | IV history usable for matched-tenor IV | `iv_surface_history` and `options_greeks_history` hold only weekly snapshots: 2026-07-17, 07-31, 08-28 and 09-04 in range, none between 08-01 and 08-27. `atm_iv` values near 4.99 occur in every bucket (trimmed at 3.0 here). Many greeks chains lack 7- and 14-DTE expiries (median chosen DTE 21 for h=5) | `p22_M2_greeks_iv.csv`; iv_surface_history distinct quote_date |

## Premise notes (spec internally consistent; measurement suggests a different quantity; no recommendation)
| spec | measured | gap size |
|---|---|---|
| ALG-10 static bias multiplier m (train median, clipped); pass band on the time-ordered test is median [0.90, 1.10] | The median σ_f/RV drifts 1.13 → 1.75 over 13 sessions. A multiplier trained on 6 sessions leaves the test median at 0.818 (h=5) and 0.851 (h=10) | 0.08 (h=5) and 0.05 (h=10) below the band floor; sd of the per-session ratio 0.19 |
| ALG-01 scales one annual forecast by √(h/252) for every h (`SCALED_CURRENT_ANNUAL_FORECAST`) | The bias depends on horizon: median RV/σ_f is 0.697 at h=5 and 0.800 at h=20 | 15% relative difference, which √-time scaling of one number cannot represent |
| Design reading: the forecast's 20–40% gap above IV is edge | Median σ_f/IV 1.08–1.25. The forecast is 25–43% above realised, and IV is 43–87% above mean \|r\|. b_F given IV is positive but fragile to the IV source at h=5 and h=20 | Gap above IV is 8–25%, not 20–40%, and it coexists with a forecast that is high against realised |
| M2(c) asks whether the forecast carries information beyond IV | The available IV is weekly and coarse in tenor, so (c) partly measures IV staleness | At h=5, b_F falls from 0.192 to 0.076 when IV error is reduced by averaging sources |

## Not tested / partial
- **(c) with exact-tenor IV on every row's forecast session: PARTIAL.** The IV history is weekly, so the 08-13 → 08-21 sessions have no surface IV. Completing it would need a daily ATM IV per ticker at 7, 14 and 28 DTE, captured at every forecast session.
- **Hidden state × direction × h cells:** INSUFFICIENT_POWER except CALL and PUT within COMPRESSED_BALANCED and LOW_ENERGY_NO_EDGE. `phase` is absent on 12 of 22 runs, so there is no phase split.
- **h=20 stability and train/test:** only 4 sessions (up to 2026-08-07) have complete 20-session windows. The h=20 train/test split was not run.
- **ALG-10 validation of an applied multiplier on baseline-eligible forecasts:** not possible, because no baseline-eligible run exists.

## Expectation vs actual (expectations.md, M2 row)
| item | expected | actual | gap |
|---|---|---|---|
| (a) forecast/realised median ratio | 1.2–1.4 (forecast high) | Median σ_f/RV 1.434 / 1.390 / 1.250 at h=5/10/20; mean F / mean \|r\| 1.61 / 1.67 / 1.59 | h=5 slightly above the range; h=10 and h=20 inside; bias direction as expected |
| (b) IV explains realised better (higher R²) | yes | Surface: h=5 yes (0.238 vs 0.183), h=10 no (0.140 vs 0.159), h=20 tie (0.118 vs 0.115). Cache and greeks: yes at all h. Pipeline IV: no at all h | Mixed, depending on IV source and tenor |
| (c) forecast coefficient not significant (\|t\| < 2) once IV is present | \|t\| < 2 | Pooled \|t\| > 2 at all h on surface IV (3.76 / 6.21 / 4.72) and on pipeline IV. \|t\| < 2 for: PUT on surface IV at all h; averaged IV at h=5 (1.57); greeks at h=20 (0.25); book IV at h=5 (1.37) | Differs on the primary proxy; agrees where IV error is lowest at h=5, and for PUT |
| n | ≈ 5,000–20,000 rows if IV is joinable, else PARTIAL (a) only | (c) n 2,389–2,935 on surface IV, 8,062 on pipeline IV; (a) n 17,275 / 13,460 / 5,172 | Smaller than expected; the weekly IV history limits (c) |
| fraction `_6_10d < _1_5d` | ≈ 100% | 100.000% (29,925 rows) | none |

## State log lines
```
M2-panel-build,MEASURED,29925,89s,"22 runs; fwd windows h5/10/20 = 19758/15940/6308; book rows 17112; dedup (ticker,session) 24530"
M2-a-forecast-vs-realised,MEASURED,17275,67s,"h5/10/20 n 17275/13460/5172; pooled R2 0.151/0.171/0.106; mean F/mean|r| 1.61/1.67/1.59"
M2-b-iv-vs-realised,PARTIAL,2389,67s,"surface IV weekly only; h5/10/20 n 2389/2935/2931; R2 IV 0.238/0.140/0.118 vs F 0.183/0.159/0.115"
M2-c-forecast-given-iv,PARTIAL,2931,67s,"surface IV stale 0-5 sessions, 8_30 bucket for h10/h20; pooled b_F 0.192/0.313/0.196 t_HC1 3.76/6.21/4.72; PUT |t|<1; G sessions 3-6"
M2-c-robustness,MEASURED,8062,40s,"FM, lag<=1, averaged IV, greeks, book IV, pipeline IV; averaged IV h5 t 1.57; greeks h20 t 0.25"
M2-greeks-iv-subsample,PARTIAL,2700,82s,"900 tickers x 3 snapshot dates; nearest-DTE median 21 for h5 (weekly expiries missing)"
M2-alg10-diagnostics,MEASURED,17275,67s,"median RV/sigma_f 0.697/0.719/0.800; IQR 0.420/0.346/0.347; coverage_1sigma 0.803/0.822/0.782; C9 report absent - derived here"
M2-stability,MEASURED,13,5s,"h5 median sigma_f/RV per session 1.126-1.747 sd 0.190; coverage 0.586-0.932"
M2-hidden-state-correction,PARTIAL,4891,5s,"2 states testable; per-state vs overall test median 0.812 vs 0.818 (h5); 4 states INSUFFICIENT_POWER n 18-93"
M2-frac-6-10-lt-1-5,MEASURED,29925,2s,"100.000%; ratio 0.4142"
M2-pipeline-gap-fields,MEASURED,4759,5s,"garch_iv_tailwind_score = IV - sigma_f vs non-ATM contract IV; matches book atm_iv-sigma_f 33.5%; zero-for-missing on 12141 forecast rows"
```
