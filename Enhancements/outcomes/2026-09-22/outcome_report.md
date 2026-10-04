# Outcome report — as of 2026-09-22

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 27188
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 1095, THESIS_ID 16128
- **invalidation_state**: MISSING 3459, VALID 23729
- **target_state**: INVALID_LEGACY 7975, LEVEL 15257, NONE 3956
- **contract_state**: MISSING 5978, SIDE_MISMATCH 1361, VALID 19849
- **direction**: BEAR 6598, BULL 19144, None 1446
- **base_state**: NOT_SCORABLE 3123, NO_ATR 11, None 1550, OK 22504
- **macro_freshness**: CURRENT 26495, STALE 693
- **outcome_state**: AMBIGUOUS 200, DATA_GAP 19, NOT_SCORABLE 3123, NOT_YET_SCORED 1550, OPEN_CENSORED 8936, STOP_FIRST 9083, TARGET_FIRST 1430, TIMEOUT 2847

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 22504 | 23 | 7.2% / 8.4% / 9.8% | 8.3% | -0.3% / +0.1% / +0.6% | 56.3% / 60.1% / 63.3% | 57.7% | +1.6% / +2.4% / +3.2% | OK |
| headline | direction=BEAR | 5568 | 22 | 5.3% / 7.5% / 10.3% | 8.3% | -1.8% / -0.8% / +0.3% | 34.1% / 38.6% / 45.0% | 36.4% | +0.5% / +2.2% / +3.9% | OK |
| headline | direction=BULL | 16936 | 22 | 7.5% / 8.9% / 10.4% | 8.6% | -0.1% / +0.3% / +0.8% | 59.9% / 64.7% / 69.2% | 62.4% | +1.4% / +2.3% / +3.3% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 14.1% | -15.6% / -14.1% / -10.0% | 27.3% / 37.5% / 60.0% | 22.2% | +9.0% / +15.3% / +29.1% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 7.0% / 11.6% / 16.1% | 16.6% | -7.8% / -5.0% / +2.0% | 41.8% / 88.4% / 92.8% | 44.8% | +4.3% / +43.5% / +45.3% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 866 | 13 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.0% | 46.0% / 63.4% / 73.2% | 53.3% | -5.4% / +10.1% / +22.3% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 10460 | 12 | 6.2% / 10.8% / 16.7% | 14.2% | -3.7% / -3.4% / -0.3% | 38.7% / 54.3% / 56.3% | 43.2% | +3.4% / +11.1% / +11.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1856 | 11 | 5.2% / 13.6% / 27.9% | 14.9% | -2.5% / -1.4% / +4.4% | 41.7% / 51.7% / 66.3% | 45.4% | +0.2% / +6.3% / +18.1% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 4 | 2 | 0.0% / 25.0% / 33.3% | 26.9% | -9.3% / -1.9% / +7.0% | 0.0% / 75.0% / 75.0% | 70.7% | -32.8% / +4.3% / +4.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 118 | 7 | 0.0% / 6.3% / 20.5% | 11.9% | -7.3% / -5.6% / +5.7% | 12.7% / 62.8% / 67.5% | 50.3% | -5.9% / +12.5% / +14.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 924 | 10 | 0.0% / 0.0% / 0.0% | 2.5% | -4.8% / -2.5% / -0.0% | 41.4% / 62.4% / 67.8% | 49.1% | +5.6% / +13.3% / +16.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 10075 | 12 | 8.0% / 10.4% / 15.4% | 14.7% | -4.9% / -4.4% / +0.1% | 39.5% / 67.6% / 71.0% | 43.5% | +4.2% / +24.1% / +25.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2868 | 19 | 5.8% / 9.4% / 21.9% | 9.1% | -2.8% / +0.3% / +2.2% | 52.5% / 64.0% / 69.1% | 61.8% | -0.4% / +2.2% / +4.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 934 | 11 | 0.0% / 0.0% / 0.0% | 1.7% | -4.1% / -1.7% / -0.0% | 51.0% / 81.7% / 85.2% | 62.8% | +7.8% / +18.8% / +20.9% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 4 | 2 | 0.0% / 25.0% / 33.3% | 26.9% | -9.3% / -1.9% / +7.0% | 0.0% / 75.0% / 75.0% | 70.7% | -32.8% / +4.3% / +4.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 143 | 8 | 0.0% / 9.4% / 17.5% | 18.5% | -12.5% / -9.1% / +0.6% | 25.3% / 61.2% / 64.3% | 44.7% | +3.8% / +16.5% / +21.9% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 10075 | 12 | 8.0% / 10.4% / 15.4% | 14.7% | -4.9% / -4.4% / +0.1% | 39.5% / 67.6% / 71.0% | 43.5% | +4.2% / +24.1% / +25.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.2% / 64.9% / 68.5% | 63.0% | +1.3% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 13950 | 21 | 18.2% / 20.9% / 25.2% | 20.5% | -0.6% / +0.4% / +1.4% | 53.3% / 55.6% / 57.7% | 52.6% | +1.6% / +3.0% / +4.4% | OK |
| headline | target_state=NONE | 996 | 9 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 29.3% / 48.1% / 51.1% | 41.5% | -4.8% / +6.6% / +8.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 3465 | 8 | 2.9% / 7.9% / 11.1% | 13.9% | -7.5% / -6.0% / -1.3% | 35.6% / 81.9% / 83.2% | 51.2% | +5.5% / +30.7% / +31.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 130 | 8 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 1.5% / 57.1% / 68.1% | 34.6% | +0.5% / +22.4% / +22.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 73 | 7 | 0.0% / 0.0% / 0.0% | 25.0% | -30.5% / -25.0% / -19.9% | 100.0% / 100.0% / 100.0% | 74.2% | +20.6% / +25.8% / +31.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.2% | -0.2% / -0.2% / -0.2% | 25.0% / 25.0% / 25.0% | 32.3% | -7.3% / -7.3% / -7.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 69 | 7 | 76.5% / 85.5% / 88.9% | 32.6% | +46.7% / +52.9% / +58.1% | 11.1% / 14.5% / 23.5% | 67.1% | -57.4% / -52.6% / -45.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 16 | 7 | 0.0% / 0.0% / 0.0% | 2.3% | -6.0% / -2.3% / +0.0% | 7.1% / 45.3% / 100.0% | 30.3% | -17.9% / +15.1% / +50.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 35 | 4 | 0.0% / 47.1% / 66.4% | 6.2% | -0.6% / +41.0% / +52.9% | 11.1% / 22.2% / 30.2% | 24.1% | -15.5% / -1.9% / +17.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 6539 | 10 | 7.2% / 9.8% / 14.1% | 13.1% | -4.0% / -3.4% / -0.0% | 40.5% / 48.2% / 50.4% | 45.2% | -1.2% / +3.0% / +6.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 2547 | 10 | 7.7% / 13.2% / 21.9% | 14.3% | -1.5% / -1.1% / +3.1% | 36.6% / 51.3% / 53.4% | 38.5% | +3.9% / +12.8% / +14.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 71 | 3 | 25.0% / 38.3% / 91.2% | 27.1% | +9.2% / +11.2% / +37.0% | 0.0% / 8.5% / 9.0% | 61.3% | -62.9% / -52.8% / -29.3% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 2.7% / 2.7% / 2.7% | 5.3% | -2.6% / -2.6% / -2.6% | 43.0% / 43.0% / 43.0% | 36.6% | +6.4% / +6.4% / +6.4% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.4% / 2.4% / 2.4% | 5.9% | -3.5% / -3.5% / -3.5% | 32.8% / 32.8% / 32.8% | 28.3% | +4.5% / +4.5% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 2.0% | -0.8% / -0.8% / -0.8% | 25.7% / 25.7% / 25.7% | 21.8% | +3.9% / +3.9% / +3.9% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 2380 | 10 | 9.4% / 12.1% / 17.0% | 14.8% | -4.3% / -2.7% / +3.6% | 32.8% / 49.7% / 55.6% | 45.7% | -6.4% / +3.9% / +8.9% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 2042 | 11 | 10.6% / 18.0% / 22.3% | 17.6% | -0.8% / +0.4% / +3.5% | 36.1% / 55.1% / 57.5% | 46.9% | -4.0% / +8.1% / +9.2% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 5629 | 11 | 6.0% / 9.4% / 15.7% | 13.5% | -4.3% / -4.1% / +0.2% | 41.4% / 60.7% / 62.1% | 42.6% | +6.0% / +18.1% / +19.0% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 1821 | 13 | 3.2% / 5.8% / 9.7% | 6.8% | -2.3% / -1.0% / +1.3% | 34.5% / 48.7% / 64.4% | 41.9% | -4.6% / +6.8% / +23.6% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 4219 | 19 | 5.7% / 8.2% / 11.6% | 9.2% | -2.0% / -1.0% / +0.3% | 33.9% / 39.0% / 45.6% | 37.1% | +0.0% / +1.9% / +3.5% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 1.7% / 3.3% / 3.8% | 3.3% | -1.0% / +0.1% / +0.4% | 16.7% / 45.0% / 57.7% | 42.4% | +0.3% / +2.5% / +4.6% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 13990 | 19 | 6.7% / 8.0% / 9.5% | 7.7% | -0.2% / +0.3% / +0.8% | 62.2% / 66.9% / 71.0% | 64.7% | +1.3% / +2.2% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 10.1% / 12.9% / 14.3% | 12.6% | -0.5% / +0.2% / +1.0% | 38.3% / 48.7% / 50.6% | 47.4% | -0.5% / +1.3% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 21831 | 22 | 7.0% / 8.1% / 9.3% | 8.0% | -0.3% / +0.1% / +0.6% | 56.3% / 60.3% / 63.7% | 58.1% | +1.5% / +2.2% / +3.0% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 7.2% / 14.9% / 24.6% | 16.3% | -1.4% / -1.4% / +0.6% | 40.7% / 51.8% / 53.6% | 43.8% | +6.4% / +7.9% / +7.9% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 11546 | 8 | 4.1% / 5.8% / 6.9% | 6.1% | -1.0% / -0.3% / +0.6% | 29.9% / 34.8% / 35.7% | 33.7% | -3.7% / +1.1% / +3.9% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.5% / 10.0% / 13.1% | 9.3% | -0.2% / +0.7% / +1.6% | 52.4% / 59.4% / 65.1% | 57.4% | +0.7% / +2.1% / +3.5% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 18209 | 20 | 6.7% / 7.9% / 9.6% | 7.8% | -0.4% / +0.1% / +0.6% | 58.6% / 62.1% / 64.9% | 59.9% | +1.5% / +2.3% / +3.2% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 7.1% / 10.1% / 12.1% | 9.9% | -0.2% / +0.2% / +0.7% | 31.3% / 45.7% / 47.8% | 44.2% | +0.2% / +1.5% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 12978 | 14 | 6.6% / 10.4% / 15.0% | 13.3% | -3.2% / -2.9% / +0.1% | 43.1% / 56.4% / 64.2% | 43.9% | +5.9% / +12.5% / +23.9% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.9% | -0.5% / +0.2% / +1.1% | 55.9% / 62.1% / 67.5% | 60.3% | +0.7% / +1.8% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 8429 | 9 | 5.7% / 8.1% / 9.7% | 8.3% | -1.1% / -0.2% / +0.4% | 39.9% / 57.1% / 65.9% | 53.7% | +1.7% / +3.4% / +5.9% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 11937 | 13 | 7.2% / 8.9% / 11.6% | 8.3% | -0.0% / +0.5% / +1.3% | 55.3% / 59.9% / 63.1% | 58.5% | +0.6% / +1.4% / +2.3% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 3.7% / 3.7% / 3.7% | 2.6% | +1.1% / +1.1% / +1.1% | 11.6% / 11.6% / 11.6% | 11.4% | +0.1% / +0.1% / +0.1% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 20782 | 22 | 7.1% / 8.3% / 9.8% | 8.2% | -0.4% / +0.1% / +0.5% | 56.3% / 60.1% / 63.4% | 57.7% | +1.7% / +2.4% / +3.2% | OK |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 4692, MARK_UNAVAILABLE 2396
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 531, RESOLUTION 3949, TIMEOUT 212

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 4692 | 21 | 13% | -57.9% | -49.1% / -44.6% / -38.8% | -1.7% | OK |
| direction=BEAR | 1021 | 21 | 22% | -48.4% | -36.7% / -26.9% / -16.4% | -3.0% | OK |
| direction=BULL | 3671 | 21 | 11% | -59.8% | -54.0% / -49.5% / -44.0% | -1.4% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 4470 | 21 | 13% | -57.1% | -49.5% / -44.7% / -38.6% | -1.8% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 531 | 10 | 25% | -76.5% | -46.2% / -38.7% / -29.9% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 3949 | 21 | 11% | -57.1% | -52.0% / -47.2% / -41.3% | -2.1% | OK |
| exit_reason=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1059 | 17 | 11% | -63.8% | -58.0% / -49.6% / -33.9% | -2.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 11 | 3 | 0% | -82.5% | -88.4% / -78.4% / -67.0% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 40 | 7 | 25% | -39.8% | -47.5% / -18.9% / +0.4% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 2872 | 11 | 11% | -54.7% | -51.8% / -46.7% / -41.1% | -2.0% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 257 | 10 | 20% | -71.4% | -48.6% / -42.1% / -38.8% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 4411 | 21 | 13% | -57.1% | -49.6% / -44.8% / -38.5% | -1.8% | OK |
| target_state=NONE | 24 | 4 | 29% | -67.3% | -86.2% / -38.9% / -29.6% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 231 | 1 | 4% | -65.1% | -60.5% / -60.5% / -60.5% | -2.9% | INSUFFICIENT_SESSIONS |
| tier=1 | 81 | 1 | 6% | -73.3% | -63.0% / -63.0% / -63.0% | -5.8% | INSUFFICIENT_SESSIONS |
| tier=2 | 81 | 1 | 1% | -75.0% | -74.3% / -74.3% / -74.3% | -3.7% | INSUFFICIENT_SESSIONS |
| tier=A | 686 | 10 | 13% | -42.2% | -44.6% / -36.8% / -28.5% | -2.1% | INSUFFICIENT_SESSIONS |
| tier=B | 829 | 11 | 18% | -46.2% | -44.9% / -37.2% / -30.1% | -1.4% | INSUFFICIENT_SESSIONS |
| tier=C | 1677 | 11 | 9% | -59.5% | -56.9% / -51.8% / -45.4% | -2.1% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 260 | 11 | 9% | -67.0% | -63.3% / -57.1% / -51.5% | -2.2% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 189 | 13 | 7% | -36.0% | -45.3% / -39.1% / -33.5% | -0.6% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 94 | 6 | 24% | -52.1% | -65.9% / -33.1% / -19.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 437 | 10 | 25% | -80.6% | -48.6% / -39.9% / -30.0% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 2966 | 21 | 0% | -66.7% | -70.8% / -64.9% / -59.1% | -4.3% | OK |
| underlying_state=TARGET_FIRST | 794 | 21 | 50% | +0.8% | +8.0% / +17.2% / +29.5% | +5.7% | OK |
| underlying_state=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |

## Forward hypothesis tests

`H9R_GAP_UP_REVERSAL` — pre-registered forward test from 2026-09-17 (SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: UP events, 10-session net return expected negative; verdict needs >= 30 event dates and >= 200 events, clustered t <= -2.0 and |mean| above the median share spread. Measurement only.

| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |
|---|---|---|---|---|---|---|---|
| UP | 5 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| UP | 10 | 0 | 0 | n/a | n/a | n/a | INSUFFICIENT_EVIDENCE |
| UP | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 5 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 10 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |

## Signal track record

Candidates considered 1499; tickets issued 5; closed 4 (Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at real prices (options: issue-time ask to exit-session bid). Decision support only.

| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | Predicted central | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 4 | 1 | 0% | -39.0% | n/a | n/a | -39.0% | -65.1% | 88.8% | +5.9% | INSUFFICIENT_EVIDENCE |
| OPTION | 4 | 1 | 0% | -39.0% | n/a | n/a | -39.0% | -65.1% | 88.8% | +5.9% | INSUFFICIENT_EVIDENCE |
| QUOTE_CURRENT_SESSION | 4 | 1 | 0% | -39.0% | n/a | n/a | -39.0% | -65.1% | 88.8% | +5.9% | INSUFFICIENT_EVIDENCE |
| QUOTE_PRIOR_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 197 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 2054 | 1402 | 1094 | 774 | 582 | 464 | 429 | 333 | 233 | 193 | 245 | 214 | 193 | 156 | 140 | 145 | 153 | 119 | 88 | 72 |
| TARGET_FIRST | 482 | 238 | 178 | 137 | 71 | 47 | 41 | 39 | 44 | 25 | 28 | 23 | 19 | 12 | 4 | 12 | 12 | 11 | 3 | 4 |

Caveats: 87 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
