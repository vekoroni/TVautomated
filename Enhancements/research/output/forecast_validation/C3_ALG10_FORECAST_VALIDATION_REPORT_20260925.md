# C3 — ALG-10 forecast-volatility validation (AVS-VAL-001): first report

**Date:** 2026-09-25 · **State:** EXPLORATORY_NO_AUTHORITY, read-only · **Harness:** `Enhancements/research/harness/forecast_validation_alg10.py` · **Report:** `alg10_report_20260925T205540Z.json`, rows `alg10_rows_20260925T205540Z.csv` (same folder)
**Governed state unchanged:** `volatility_budget.bias_multiplier = 1.0`, `bias_multiplier_approved = false`, `validation_state = UNVALIDATED`. This report does not change them; it says what the data says.

## 1. What was measured

Every stored point-in-time Layer 3 forecast (28,731 forecasts across 27 runs, one per ticker and session, session from the run's `bar_data_asof`) against realised close-to-close volatility over the next 5, 10 and 20 sessions from the canonical price store (last close 2026-09-24), per ALG-10: ratio realised ÷ forecast, 1σ coverage, and QLIKE on variance as the reviewer asked. Two forecast families are kept apart: the legacy Layer 3 output used until the 17 Sep integrity fix, and the current model (`FORECAST_OK`, raw unclipped).

## 2. Result

| Family | h | Matured rows | Sessions | Median realised ÷ forecast | 95% CI, session blocks | IQR | 1σ coverage (0.68 if unbiased) | QLIKE (variance) |
|---|---|---|---|---|---|---|---|---|
| Legacy (14 Aug – 16 Sep) | 5 | 19,514 | 14 | **0.674** | 0.644 – 0.701 | 0.50 – 0.88 | 0.818 | 0.514 |
| Legacy | 10 | 15,147 | 11 | **0.708** | 0.680 – 0.729 | 0.57 – 0.87 | 0.809 | 0.371 |
| Legacy | 20 | 5,520 | 4 | **0.716** | 0.686 – 0.742 | 0.60 – 0.85 | 0.794 | 0.325 |
| Current v2 (17 Sep only) | 5 | 1,497 | 1 | 0.715 | — | 0.54 – 0.92 | 0.751 | 0.440 |
| Current v2 | 10, 20 | 0 | 0 | no matured windows yet | | | | |

Continuity across the 17 Sep fix, same ticker on adjacent sessions: the current model's forecast is 0.91 × the legacy forecast (p10 0.88, p90 0.93; n = 1,584). The fix lowered the level by about 9%; the gap below is about 30%.

**By hidden state (legacy, h = 5):** every bucket sits between 0.61 and 0.74 (COMPRESSED_BALANCED 0.680, LOW_ENERGY_NO_EDGE 0.672, COMPRESSED_BEARISH_FORCE 0.646, TRENDING_BULLISH_INERTIA 0.702, TRENDING_BEARISH_INERTIA 0.605, COMPRESSED_BULLISH_FORCE 0.736). The bias is not a state effect.

**By session (legacy, h = 5):** the session medians run from 0.56 (20 Aug) to 0.77 (14 Aug); no session reaches 0.80. 84.6% of individual forecasts exceeded the realised volatility that followed.

## 3. Reading

1. **The forecast runs about 30% high, at every horizon, in every state, on every session measured.** The candidate ALG-10 multiplier is roughly 0.70 (clipped range 0.5–1.5); the current model, 9% lower than legacy, would still carry a multiplier near 0.78 if its single matured session is representative.
2. **Coverage confirms the direction:** 79–82% of moves fell inside ±1σ where 68% should, so the budget is too wide, and the reachable target it implies is too far.
3. **This is the artefact AVS-RANK-001 §4 and ALG-10 warned about.** With the harness's bias sweep already run, a multiplier of 0.70 takes the 24 Sep grid-positive rows from 31 to 13, and the reachable payoff of the median row from +56% to +28%. Every "cheap convexity" reading in this week's research assumed a multiplier of 1.0 and is therefore optimistic by about this amount. The register's amendment on C3 stands: no value-based promotion before this is resolved.
4. **The governed pass test cannot be run yet.** ALG-10 requires a time-ordered test partition with a purge of h sessions; with 14 sessions at h = 5 the purge leaves no test sessions, and the current model has one matured session. The harness reports this as `INSUFFICIENT_SESSIONS_FOR_TIME_ORDERED_TEST` rather than fitting on everything and calling it validated.

## 4. What should happen

| Action | Owner | When |
|---|---|---|
| Keep `bias_multiplier_approved = false` and `validation_state = UNVALIDATED`; ALG-10 says m = 1.0 until the test passes, and the test cannot yet be run | ACK / config | now, no change |
| Stop describing any row as "cheap convexity" or "forecast above IV" as if the forecast were the truth; the trading-plan flag `FORECAST_ABOVE_IV` reads as a warning, which is what it is | presentation (E1/E2) | now |
| Re-run this harness weekly. The current model's h = 5 test partition becomes possible at about 24 sessions (mid to late October); h = 10 and h = 20 later. The legacy family already gives the direction | research | weekly |
| Investigate the Layer 3 model rather than only scaling it: a uniform 30% overshoot across states and sessions points at the estimator (annualisation, mean-reversion target, or the GARCH persistence) rather than at regime. The 17 Sep fix moved the level 9% and not the shape | Volatility context owner, test-first | root cause before any multiplier |
| Register this run's variant count: one (the ALG-10 method as specified, no alternatives tried) | cohort registration | with the next amendment |

## 5. Limits

Realised volatility is close-to-close; ALG-10 specifies close-to-close, so that is by design, but an intraday-range estimate would read higher and narrow the gap somewhat. The legacy family is not the model in production today. Sessions overlap for h = 10 and h = 20, so the confidence intervals by session block are the honest ones and the row counts are not independent observations. No transaction or outcome data enters this report; it is about the forecast only.
