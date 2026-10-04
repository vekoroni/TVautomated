# Outcome report — as of 2026-09-18

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 22951
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 753, THESIS_ID 12233
- **invalidation_state**: MISSING 2667, VALID 20284
- **target_state**: INVALID_LEGACY 7842, LEVEL 11917, NONE 3192
- **contract_state**: MISSING 5622, SIDE_MISMATCH 1361, VALID 15968
- **direction**: BEAR 5479, BULL 16360, None 1112
- **base_state**: NOT_SCORABLE 2321, NO_ATR 11, None 1549, OK 19070
- **macro_freshness**: CURRENT 22258, STALE 693
- **outcome_state**: AMBIGUOUS 130, DATA_GAP 17, NOT_SCORABLE 2321, NOT_YET_SCORED 1549, OPEN_CENSORED 7031, STOP_FIRST 8102, TARGET_FIRST 1173, TIMEOUT 2628

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 19070 | 21 | 6.8% / 8.0% / 9.6% | 8.0% | -0.3% / +0.1% / +0.6% | 56.9% / 61.0% / 64.4% | 59.0% | +1.4% / +2.0% / +2.6% | OK |
| headline | direction=BEAR | 4569 | 20 | 5.4% / 7.8% / 11.2% | 8.8% | -1.9% / -0.9% / +0.4% | 32.2% / 37.9% / 45.4% | 36.5% | -0.1% / +1.4% / +2.9% | OK |
| headline | direction=BULL | 14501 | 20 | 6.8% / 8.3% / 9.9% | 8.1% | -0.2% / +0.3% / +0.7% | 60.5% / 65.7% / 70.2% | 63.6% | +1.2% / +2.1% / +3.0% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 10.4% | -12.8% / -10.4% / -6.9% | 27.3% / 37.5% / 60.0% | 20.0% | +10.9% / +17.5% / +32.2% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 4.1% / 8.4% / 14.6% | 12.8% | -6.3% / -4.4% / +0.4% | 37.5% / 67.0% / 69.5% | 43.7% | +2.5% / +23.3% / +25.7% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 853 | 11 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 39.4% / 47.1% / 53.4% | 53.5% | -12.0% / -6.4% / +0.7% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 7039 | 10 | 5.6% / 14.9% / 19.7% | 12.9% | -0.6% / +2.0% / +3.2% | 34.6% / 45.3% / 51.2% | 42.4% | +0.3% / +3.0% / +4.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1811 | 9 | 3.5% / 18.1% / 28.5% | 15.4% | -1.4% / +2.7% / +5.9% | 38.1% / 43.4% / 51.3% | 42.2% | -5.4% / +1.2% / +3.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.8% | +7.6% / +7.6% / +7.6% | 66.7% / 66.7% / 66.7% | 70.8% | -4.1% / -4.1% / -4.1% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 71 | 5 | 0.0% / 9.1% / 31.5% | 10.4% | -4.3% / -1.3% / +15.7% | 17.9% / 43.1% / 58.0% | 52.4% | -17.8% / -9.3% / +6.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 892 | 8 | 0.0% / 0.0% / 0.0% | 2.1% | -4.7% / -2.1% / -0.0% | 28.9% / 45.4% / 57.0% | 49.7% | -6.1% / -4.2% / +4.1% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 6766 | 10 | 6.1% / 12.0% / 16.7% | 11.3% | -1.5% / +0.7% / +2.4% | 35.4% / 52.7% / 65.5% | 43.6% | +1.8% / +9.1% / +14.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2823 | 17 | 5.1% / 8.9% / 23.4% | 8.8% | -1.2% / +0.1% / +2.7% | 50.4% / 65.6% / 70.2% | 64.5% | -2.1% / +1.1% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 902 | 9 | 0.0% / 0.0% / 0.0% | 1.6% | -4.2% / -1.6% / -0.0% | 37.1% / 77.8% / 85.2% | 65.8% | -4.8% / +12.0% / +17.6% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.8% | +7.6% / +7.6% / +7.6% | 66.7% / 66.7% / 66.7% | 70.8% | -4.1% / -4.1% / -4.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 96 | 6 | 0.0% / 12.2% / 22.2% | 18.5% | -10.4% / -6.3% / +7.5% | 22.5% / 57.6% / 59.8% | 45.2% | -15.1% / +12.5% / +20.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 6766 | 10 | 6.1% / 12.0% / 16.7% | 11.3% | -1.5% / +0.7% / +2.4% | 35.4% / 52.7% / 65.5% | 43.6% | +1.8% / +9.1% / +14.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.4% / 65.1% / 68.8% | 63.2% | +1.2% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 10641 | 19 | 19.1% / 22.3% / 27.2% | 21.7% | -0.5% / +0.5% / +1.8% | 53.2% / 55.9% / 58.0% | 53.8% | +0.9% / +2.1% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | target_state=NONE | 871 | 7 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 26.4% / 35.2% / 44.3% | 42.3% | -10.9% / -7.1% / +0.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 2521 | 6 | 1.8% / 7.2% / 11.4% | 11.8% | -4.8% / -4.6% / -1.5% | 31.0% / 65.3% / 73.8% | 54.3% | +3.9% / +10.9% / +12.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 105 | 6 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.0% / 33.7% / 51.2% | 40.1% | -8.5% / -6.4% / +1.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 50 | 5 | 0.0% / 0.0% / 0.0% | 24.7% | -30.7% / -24.7% / -15.3% | 100.0% / 100.0% / 100.0% | 74.2% | +19.1% / +25.8% / +32.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 21.9% / 21.9% / 21.9% | 28.7% | -6.8% / -6.8% / -6.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 47 | 5 | 60.0% / 87.2% / 100.0% | 34.6% | +27.8% / +52.6% / +66.2% | 0.0% / 12.8% / 40.0% | 64.8% | -61.9% / -52.1% / -26.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 9 | 5 | 0.0% / 0.0% / 0.0% | 1.2% | -2.7% / -1.2% / +0.0% | 18.2% / 66.7% / 100.0% | 23.2% | +0.7% / +43.4% / +74.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 13 | 3 | 0.0% / 15.4% / 33.3% | 5.1% | -0.7% / +10.3% / +23.6% | 7.7% / 15.4% / 23.1% | 20.6% | -16.6% / -5.2% / +8.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 5107 | 8 | 6.8% / 10.1% / 15.8% | 10.9% | -1.4% / -0.9% / +2.3% | 37.8% / 43.7% / 47.4% | 45.1% | -4.1% / -1.4% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 1654 | 8 | 4.7% / 19.5% / 25.6% | 14.7% | -1.5% / +4.8% / +6.9% | 31.1% / 40.4% / 45.0% | 33.9% | +1.7% / +6.4% / +9.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 5 | 2 | 25.0% / 40.0% / 100.0% | 24.4% | +15.6% / +15.6% / +41.8% | 0.0% / 0.0% / 0.0% | 63.9% | -63.9% / -63.9% / -32.2% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 2.3% / 2.3% / 2.3% | 4.4% | -2.1% / -2.1% / -2.1% | 39.2% / 39.2% / 39.2% | 32.8% | +6.4% / +6.4% / +6.4% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.0% / 2.0% / 2.0% | 4.9% | -2.9% / -2.9% / -2.9% | 24.1% / 24.1% / 24.1% | 24.2% | -0.1% / -0.1% / -0.1% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 1.5% | -0.3% / -0.3% / -0.3% | 20.8% / 20.8% / 20.8% | 18.1% | +2.7% / +2.7% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 1271 | 8 | 6.5% / 9.3% / 18.7% | 13.2% | -4.7% / -3.9% / +3.5% | 25.5% / 52.9% / 55.8% | 45.2% | -12.8% / +7.7% / +9.5% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 1466 | 9 | 6.7% / 18.0% / 23.1% | 17.1% | -1.2% / +0.9% / +2.3% | 33.1% / 46.6% / 53.4% | 45.8% | -5.4% / +0.9% / +3.6% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 4065 | 9 | 5.0% / 14.8% / 19.6% | 11.6% | -1.3% / +3.2% / +4.8% | 37.2% / 42.9% / 53.9% | 41.3% | +1.0% / +1.6% / +7.3% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 1636 | 11 | 4.0% / 6.3% / 11.3% | 6.2% | -0.6% / +0.0% / +3.1% | 32.5% / 39.0% / 46.8% | 41.3% | -5.5% / -2.3% / +3.4% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 3220 | 17 | 5.7% / 8.7% / 12.6% | 9.6% | -2.1% / -0.9% / +0.6% | 32.5% / 38.3% / 45.6% | 36.8% | -0.2% / +1.5% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 0.9% / 2.5% / 3.0% | 3.5% | -1.0% / -1.0% / -0.2% | 11.6% / 47.3% / 63.5% | 45.9% | -2.0% / +1.4% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 11555 | 17 | 6.1% / 7.4% / 9.0% | 7.1% | -0.3% / +0.3% / +0.8% | 63.3% / 67.9% / 72.2% | 65.8% | +1.1% / +2.1% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 7.7% / 12.2% / 14.1% | 11.9% | -0.9% / +0.3% / +1.1% | 37.7% / 49.6% / 50.1% | 48.7% | -0.2% / +0.9% / +2.3% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 18397 | 20 | 6.5% / 7.6% / 8.9% | 7.6% | -0.4% / +0.0% / +0.5% | 57.1% / 61.3% / 64.7% | 59.4% | +1.2% / +2.0% / +2.6% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 7.1% / 17.5% / 25.4% | 15.6% | +0.5% / +1.9% / +2.9% | 35.8% / 44.7% / 49.5% | 40.9% | +2.6% / +3.8% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 8112 | 6 | 1.9% / 3.7% / 5.2% | 4.4% | -1.4% / -0.7% / -0.0% | 25.5% / 30.7% / 31.9% | 29.2% | -4.4% / +1.5% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.5% / 9.9% / 13.1% | 9.2% | -0.1% / +0.7% / +1.7% | 52.0% / 59.4% / 65.2% | 57.7% | +0.3% / +1.7% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 14775 | 18 | 6.2% / 7.5% / 9.3% | 7.4% | -0.4% / +0.1% / +0.7% | 59.4% / 63.0% / 65.9% | 61.0% | +1.3% / +2.1% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 5.2% / 9.6% / 12.2% | 9.5% | -0.8% / +0.1% / +0.8% | 27.9% / 46.6% / 48.9% | 45.8% | +0.1% / +0.7% / +1.9% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 9544 | 12 | 5.3% / 12.8% / 17.6% | 11.9% | -1.0% / +0.9% / +2.4% | 36.7% / 46.3% / 51.5% | 42.7% | -3.0% / +3.6% / +4.8% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.9% | -0.5% / +0.2% / +1.1% | 55.9% / 62.2% / 67.6% | 60.3% | +0.7% / +1.8% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.0% / 7.1% / 9.7% | 7.6% | -1.2% / -0.5% / +0.1% | 65.2% / 68.8% / 74.7% | 66.0% | +2.5% / +2.8% / +4.4% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 7916 | 8 | 4.4% / 7.5% / 9.3% | 7.8% | -1.0% / -0.2% / +0.3% | 32.8% / 58.7% / 67.2% | 56.0% | +0.8% / +2.7% / +4.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 9016 | 11 | 6.8% / 8.6% / 11.6% | 8.0% | -0.0% / +0.6% / +1.6% | 55.3% / 60.7% / 64.2% | 59.7% | +0.1% / +1.1% / +1.9% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 19070 | 21 | 6.8% / 8.0% / 9.6% | 8.0% | -0.3% / +0.1% / +0.6% | 56.9% / 61.0% / 64.4% | 59.0% | +1.4% / +2.0% / +2.6% | OK |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 3582, MARK_UNAVAILABLE 2322
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 531, RESOLUTION 2840, TIMEOUT 211

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 3582 | 19 | 14% | -62.1% | -50.6% / -45.8% / -39.6% | -1.6% | INSUFFICIENT_SESSIONS |
| direction=BEAR | 777 | 19 | 28% | -46.6% | -29.7% / -19.3% / -9.7% | -1.4% | INSUFFICIENT_SESSIONS |
| direction=BULL | 2805 | 19 | 10% | -65.0% | -57.2% / -53.2% / -48.0% | -1.6% | INSUFFICIENT_SESSIONS |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 3360 | 19 | 14% | -61.6% | -51.0% / -46.1% / -39.3% | -1.7% | INSUFFICIENT_SESSIONS |
| exit_reason=CONTRACT_LAST_USABLE | 531 | 10 | 25% | -76.5% | -46.2% / -38.7% / -29.9% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 2840 | 19 | 10% | -61.8% | -54.2% / -49.7% / -43.7% | -2.2% | INSUFFICIENT_SESSIONS |
| exit_reason=TIMEOUT | 211 | 5 | 35% | -44.8% | -22.9% / -10.9% / -0.1% | +6.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 942 | 15 | 12% | -63.7% | -57.6% / -49.3% / -32.7% | -2.3% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0% | -85.8% | -97.6% / -82.9% / -76.6% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 33 | 5 | 30% | -50.3% | -49.9% / -14.2% / +5.6% | -3.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 1887 | 9 | 11% | -61.1% | -54.9% / -50.5% / -43.8% | -2.1% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 257 | 10 | 20% | -71.4% | -48.6% / -42.1% / -38.8% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 3302 | 19 | 13% | -61.6% | -51.1% / -46.2% / -39.2% | -1.7% | INSUFFICIENT_SESSIONS |
| target_state=NONE | 23 | 3 | 30% | -85.7% | -91.5% / -39.1% / -29.7% | n/a | INSUFFICIENT_SESSIONS |
| tier=0 | 211 | 1 | 4% | -64.9% | -60.5% / -60.5% / -60.5% | -2.8% | INSUFFICIENT_SESSIONS |
| tier=1 | 63 | 1 | 6% | -68.8% | -58.9% / -58.9% / -58.9% | -4.4% | INSUFFICIENT_SESSIONS |
| tier=2 | 66 | 1 | 2% | -71.5% | -72.5% / -72.5% / -72.5% | -3.1% | INSUFFICIENT_SESSIONS |
| tier=A | 383 | 8 | 13% | -54.0% | -48.6% / -42.2% / -31.6% | -2.7% | INSUFFICIENT_SESSIONS |
| tier=B | 644 | 9 | 16% | -55.3% | -52.7% / -41.4% / -30.9% | -1.9% | INSUFFICIENT_SESSIONS |
| tier=C | 1161 | 9 | 9% | -63.6% | -58.6% / -53.4% / -47.1% | -2.0% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 208 | 9 | 10% | -70.2% | -63.4% / -56.6% / -51.2% | -1.3% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 120 | 11 | 6% | -37.8% | -49.2% / -41.1% / -32.6% | -0.7% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 94 | 6 | 24% | -52.1% | -65.9% / -33.1% / -19.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 437 | 10 | 25% | -80.6% | -48.6% / -39.9% / -30.0% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 2156 | 19 | 0% | -70.2% | -73.1% / -67.6% / -62.9% | -4.3% | INSUFFICIENT_SESSIONS |
| underlying_state=TARGET_FIRST | 564 | 19 | 50% | +0.4% | +3.5% / +16.6% / +33.7% | +5.5% | INSUFFICIENT_SESSIONS |
| underlying_state=TIMEOUT | 211 | 5 | 35% | -44.8% | -22.9% / -10.9% / -0.1% | +6.5% | INSUFFICIENT_SESSIONS |

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

Candidates considered 1499; tickets issued 5; closed 2 (Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at real prices (options: issue-time ask to exit-session bid). Decision support only.

| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | Predicted central | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 2 | 1 | 0% | -38.2% | n/a | n/a | -38.2% | -65.1% | 69.1% | +4.4% | INSUFFICIENT_EVIDENCE |
| OPTION | 2 | 1 | 0% | -38.2% | n/a | n/a | -38.2% | -65.1% | 69.1% | +4.4% | INSUFFICIENT_EVIDENCE |
| QUOTE_CURRENT_SESSION | 2 | 1 | 0% | -38.2% | n/a | n/a | -38.2% | -65.1% | 69.1% | +4.4% | INSUFFICIENT_EVIDENCE |
| QUOTE_PRIOR_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 128 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 1751 | 1211 | 947 | 715 | 554 | 403 | 359 | 274 | 225 | 180 | 233 | 204 | 188 | 152 | 132 | 145 | 153 | 119 | 88 | 69 |
| TARGET_FIRST | 373 | 200 | 135 | 117 | 62 | 39 | 31 | 30 | 44 | 25 | 22 | 19 | 19 | 12 | 4 | 12 | 12 | 11 | 3 | 3 |

Caveats: 86 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
