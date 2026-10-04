# Outcome report — as of 2026-09-17

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `6dcaf4e566f49367` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 21189
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 566, THESIS_ID 10658
- **invalidation_state**: MISSING 2301, VALID 18888
- **target_state**: INVALID_LEGACY 7771, LEVEL 10586, NONE 2832
- **contract_state**: MISSING 5429, SIDE_MISMATCH 1361, VALID 14399
- **direction**: BEAR 4995, BULL 15266, None 928
- **base_state**: NOT_SCORABLE 1843, NO_ATR 11, None 2777, OK 16558
- **macro_freshness**: CURRENT 20496, STALE 693
- **outcome_state**: AMBIGUOUS 99, DATA_GAP 21, NOT_SCORABLE 1843, NOT_YET_SCORED 2777, OPEN_CENSORED 5489, STOP_FIRST 7533, TARGET_FIRST 1143, TIMEOUT 2284

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 16558 | 20 | 7.1% / 8.4% / 10.0% | 8.2% | -0.3% / +0.2% / +0.7% | 56.8% / 60.8% / 64.2% | 58.8% | +1.3% / +2.0% / +2.6% | OK |
| headline | direction=BEAR | 3849 | 19 | 5.5% / 8.1% / 11.6% | 8.5% | -1.5% / -0.4% / +1.1% | 32.7% / 38.4% / 46.3% | 38.1% | -1.4% / +0.2% / +2.0% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL | 12709 | 19 | 7.3% / 8.8% / 10.4% | 8.4% | -0.2% / +0.3% / +0.8% | 59.9% / 65.1% / 69.8% | 62.9% | +1.3% / +2.2% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 10.3% | -12.4% / -10.3% / -6.7% | 27.3% / 37.5% / 60.0% | 17.6% | +12.9% / +19.9% / +35.3% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1076 | 8 | 4.3% / 10.3% / 17.2% | 13.3% | -6.5% / -3.1% / +1.9% | 34.0% / 62.8% / 66.2% | 44.6% | -0.2% / +18.2% / +20.8% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 158 | 10 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 39.0% / 46.9% / 55.7% | 50.8% | -10.0% / -3.9% / +4.7% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 5790 | 9 | 6.5% / 15.8% / 20.7% | 13.9% | -0.2% / +1.8% / +3.5% | 33.3% / 44.8% / 49.9% | 42.0% | +0.7% / +2.7% / +4.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1794 | 8 | 3.9% / 18.5% / 29.5% | 15.8% | -0.9% / +2.6% / +6.8% | 37.7% / 41.8% / 49.3% | 41.7% | -5.3% / +0.1% / +5.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.7% | +7.7% / +7.7% / +7.7% | 66.7% / 66.7% / 66.7% | 70.3% | -3.6% / -3.6% / -3.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 41 | 4 | 0.0% / 9.2% / 30.7% | 11.0% | -4.6% / -1.8% / +14.4% | 15.2% / 40.4% / 55.8% | 51.3% | -14.7% / -11.0% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 147 | 7 | 0.0% / 0.0% / 0.0% | 2.5% | -5.2% / -2.5% / +0.0% | 27.8% / 48.9% / 59.7% | 48.0% | -4.9% / +0.9% / +11.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 5046 | 9 | 7.2% / 9.9% / 16.6% | 12.3% | -3.4% / -2.3% / +1.4% | 33.6% / 56.6% / 60.8% | 44.3% | +1.8% / +12.3% / +13.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2806 | 16 | 5.3% / 9.1% / 25.5% | 9.0% | -1.2% / +0.1% / +3.9% | 49.5% / 65.9% / 69.7% | 64.6% | -3.0% / +1.3% / +2.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 157 | 8 | 0.0% / 0.0% / 0.0% | 1.9% | -4.7% / -1.9% / +0.0% | 35.7% / 79.3% / 86.2% | 64.7% | -2.8% / +14.5% / +21.8% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.7% | +7.7% / +7.7% / +7.7% | 66.7% / 66.7% / 66.7% | 70.3% | -3.6% / -3.6% / -3.6% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 66 | 5 | 0.0% / 13.8% / 20.5% | 18.1% | -7.5% / -4.3% / +5.2% | 17.4% / 56.3% / 57.4% | 44.2% | -14.1% / +12.1% / +18.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 5046 | 9 | 7.2% / 9.9% / 16.6% | 12.3% | -3.4% / -2.3% / +1.4% | 33.6% / 56.6% / 60.8% | 44.3% | +1.8% / +12.3% / +13.2% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.8% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.6% / 65.2% / 68.9% | 63.1% | +1.2% / +2.0% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 8914 | 18 | 21.0% / 24.1% / 29.3% | 23.2% | -0.2% / +0.9% / +2.3% | 52.5% / 55.2% / 57.4% | 53.4% | +0.5% / +1.8% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | target_state=NONE | 86 | 6 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 26.0% / 36.1% / 47.2% | 39.4% | -10.3% / -3.4% / +8.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 2352 | 5 | 2.2% / 4.4% / 11.9% | 12.7% | -8.5% / -8.3% / -1.4% | 27.6% / 64.8% / 71.9% | 52.8% | +3.2% / +12.0% / +12.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 98 | 5 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.0% / 41.4% / 57.9% | 42.2% | -8.8% / -0.8% / +4.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 34 | 4 | 0.0% / 0.0% / 0.0% | 29.6% | -31.5% / -29.6% / -21.7% | 100.0% / 100.0% / 100.0% | 69.2% | +22.9% / +30.8% / +37.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 21.9% / 21.9% / 21.9% | 26.2% | -4.3% / -4.3% / -4.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 46 | 4 | 88.3% / 89.1% / 100.0% | 34.5% | +53.5% / +54.7% / +77.8% | 0.0% / 10.9% / 11.7% | 64.9% | -77.7% / -54.0% / -52.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 6 | 4 | 0.0% / 0.0% / 0.0% | 1.0% | -2.3% / -1.0% / +0.0% | 0.0% / 37.5% / 52.6% | 24.2% | -23.4% / +13.3% / +49.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 13 | 3 | 0.0% / 15.4% / 33.3% | 5.1% | -0.7% / +10.3% / +23.8% | 7.7% / 15.4% / 23.1% | 19.2% | -14.9% / -3.8% / +9.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 3435 | 7 | 8.3% / 13.3% / 19.5% | 12.4% | -0.2% / +0.9% / +3.9% | 35.4% / 42.8% / 47.1% | 44.4% | -4.8% / -1.6% / +3.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 1010 | 7 | 6.0% / 21.7% / 26.9% | 15.6% | -0.5% / +6.1% / +8.2% | 29.4% / 33.9% / 40.3% | 32.8% | -0.3% / +1.1% / +6.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 5 | 2 | 0.0% / 20.0% / 100.0% | 24.2% | -4.2% / -4.2% / +42.0% | 0.0% / 0.0% / 0.0% | 65.0% | -65.0% / -65.0% / -30.1% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 2.3% / 2.3% / 2.3% | 4.2% | -1.9% / -1.9% / -1.9% | 35.9% / 35.9% / 35.9% | 29.8% | +6.2% / +6.2% / +6.2% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.0% / 2.0% / 2.0% | 4.4% | -2.4% / -2.4% / -2.4% | 19.8% / 19.8% / 19.8% | 22.0% | -2.2% / -2.2% / -2.2% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 1.4% | -0.2% / -0.2% / -0.2% | 18.0% / 18.0% / 18.0% | 15.9% | +2.2% / +2.2% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 932 | 7 | 6.7% / 18.0% / 23.8% | 14.3% | -0.6% / +3.7% / +7.8% | 23.8% / 39.3% / 47.9% | 44.8% | -13.9% / -5.4% / -1.7% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 1161 | 8 | 7.5% / 18.2% / 23.6% | 18.2% | -0.2% / +0.0% / +2.1% | 29.5% / 40.8% / 46.6% | 44.8% | -7.2% / -4.0% / -2.1% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 3086 | 8 | 5.4% / 15.7% / 20.5% | 12.6% | -1.3% / +3.1% / +5.6% | 36.3% / 51.0% / 55.2% | 41.3% | +3.8% / +9.6% / +10.3% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 747 | 10 | 6.2% / 9.4% / 14.0% | 7.5% | +0.8% / +2.0% / +5.4% | 35.0% / 41.6% / 48.7% | 39.6% | -4.1% / +2.0% / +7.3% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 2500 | 16 | 5.8% / 8.8% / 12.6% | 9.3% | -1.7% / -0.5% / +1.0% | 32.8% / 38.8% / 46.8% | 38.2% | -1.4% / +0.7% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 0.8% / 2.3% / 2.8% | 3.4% | -1.1% / -1.1% / -0.0% | 9.5% / 51.2% / 66.4% | 50.5% | -2.0% / +0.8% / +0.8% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 9763 | 16 | 6.4% / 7.7% / 9.3% | 7.4% | -0.2% / +0.3% / +0.9% | 62.7% / 67.4% / 71.6% | 65.1% | +1.3% / +2.3% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 8.5% / 13.1% / 15.4% | 12.7% | -0.6% / +0.4% / +1.1% | 34.4% / 48.3% / 49.3% | 47.7% | +0.5% / +0.6% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 15885 | 19 | 6.9% / 8.0% / 9.3% | 7.9% | -0.4% / +0.1% / +0.6% | 57.0% / 61.1% / 64.6% | 59.2% | +1.2% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=STALE | 673 | 3 | 7.4% / 19.3% / 25.4% | 15.5% | +0.6% / +3.8% / +5.8% | 34.6% / 42.6% / 46.9% | 40.9% | -1.0% / +1.7% / +4.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.7% / 66.1% | 62.0% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 5600 | 5 | 2.2% / 4.4% / 5.7% | 4.9% | -1.3% / -0.5% / +0.0% | 20.5% / 26.7% / 27.9% | 27.3% | -6.1% / -0.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.5% / 10.0% / 13.1% | 9.1% | -0.0% / +0.8% / +1.8% | 52.1% / 59.4% / 65.0% | 57.6% | +0.4% / +1.8% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 12263 | 17 | 6.5% / 7.8% / 9.7% | 7.7% | -0.4% / +0.2% / +0.8% | 59.3% / 62.8% / 65.6% | 60.7% | +1.3% / +2.1% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 5.6% / 10.4% / 13.3% | 10.2% | -0.5% / +0.2% / +0.8% | 25.3% / 46.2% / 48.5% | 46.1% | -0.0% / +0.1% / +1.4% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.3% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 7032 | 11 | 6.3% / 14.2% / 18.6% | 13.1% | -0.6% / +1.1% / +3.0% | 35.4% / 45.0% / 49.2% | 42.1% | +0.2% / +2.9% / +4.6% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.8% | -0.5% / +0.2% / +1.2% | 55.9% / 62.1% / 67.3% | 60.2% | +0.8% / +1.9% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.0% / 7.1% / 9.7% | 7.6% | -1.2% / -0.5% / +0.2% | 65.1% / 68.3% / 71.8% | 65.6% | +2.5% / +2.7% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 7916 | 8 | 4.5% / 7.9% / 9.8% | 8.0% | -1.0% / -0.1% / +0.4% | 31.9% / 58.8% / 67.0% | 56.3% | +0.3% / +2.5% / +4.3% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 6504 | 10 | 7.2% / 9.0% / 12.2% | 8.3% | +0.0% / +0.7% / +1.8% | 54.4% / 60.0% / 63.6% | 58.9% | +0.0% / +1.1% / +1.9% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 16558 | 20 | 7.1% / 8.4% / 10.0% | 8.2% | -0.3% / +0.2% / +0.7% | 56.8% / 60.8% / 64.2% | 58.8% | +1.3% / +2.0% / +2.6% | OK |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1422, ENTRY_NOT_VALUED 1845, MARKED 3127, MARK_UNAVAILABLE 2294
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 531, RESOLUTION 2385, TIMEOUT 211

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 3127 | 18 | 15% | -62.9% | -49.6% / -45.0% / -38.4% | -1.4% | INSUFFICIENT_SESSIONS |
| direction=BEAR | 695 | 18 | 30% | -46.2% | -26.0% / -16.2% / -6.5% | -0.6% | INSUFFICIENT_SESSIONS |
| direction=BULL | 2432 | 18 | 11% | -66.4% | -57.4% / -53.2% / -47.9% | -1.5% | INSUFFICIENT_SESSIONS |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 2905 | 18 | 15% | -62.5% | -50.0% / -45.2% / -38.0% | -1.5% | INSUFFICIENT_SESSIONS |
| exit_reason=CONTRACT_LAST_USABLE | 531 | 10 | 25% | -76.5% | -46.2% / -38.7% / -29.9% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 2385 | 18 | 12% | -62.5% | -53.9% / -49.4% / -42.9% | -2.1% | INSUFFICIENT_SESSIONS |
| exit_reason=TIMEOUT | 211 | 5 | 35% | -44.8% | -22.9% / -10.9% / -0.1% | +6.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 880 | 14 | 13% | -63.3% | -57.2% / -48.5% / -34.4% | -2.1% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0% | -85.8% | -97.6% / -82.9% / -76.6% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 29 | 4 | 34% | -51.1% | -55.5% / -10.5% / +6.2% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 1498 | 8 | 12% | -62.6% | -54.8% / -50.6% / -44.3% | -1.9% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 257 | 10 | 20% | -71.4% | -48.6% / -42.1% / -38.8% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 2847 | 18 | 15% | -62.5% | -50.2% / -45.3% / -37.9% | -1.5% | INSUFFICIENT_SESSIONS |
| target_state=NONE | 23 | 3 | 30% | -85.7% | -91.5% / -39.1% / -29.7% | n/a | INSUFFICIENT_SESSIONS |
| tier=0 | 194 | 1 | 4% | -63.2% | -59.2% / -59.2% / -59.2% | -2.7% | INSUFFICIENT_SESSIONS |
| tier=1 | 53 | 1 | 8% | -67.1% | -56.4% / -56.4% / -56.4% | -3.7% | INSUFFICIENT_SESSIONS |
| tier=2 | 57 | 1 | 2% | -71.6% | -72.8% / -72.8% / -72.8% | -2.8% | INSUFFICIENT_SESSIONS |
| tier=A | 298 | 7 | 13% | -55.5% | -48.0% / -42.7% / -31.4% | -2.3% | INSUFFICIENT_SESSIONS |
| tier=B | 549 | 8 | 19% | -56.6% | -53.1% / -40.2% / -29.4% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=C | 949 | 8 | 11% | -65.9% | -58.5% / -53.5% / -47.2% | -2.0% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 181 | 8 | 11% | -73.7% | -63.8% / -56.2% / -50.5% | -1.3% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 92 | 10 | 3% | -41.9% | -50.7% / -45.9% / -38.3% | -0.7% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 94 | 6 | 24% | -52.1% | -65.9% / -33.1% / -19.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 437 | 10 | 25% | -80.6% | -48.6% / -39.9% / -30.0% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 1753 | 18 | 0% | -72.5% | -75.4% / -69.8% / -66.6% | -4.5% | INSUFFICIENT_SESSIONS |
| underlying_state=TARGET_FIRST | 540 | 18 | 49% | -1.8% | +2.5% / +16.3% / +34.0% | +5.6% | INSUFFICIENT_SESSIONS |
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

Candidates considered 0; tickets issued 0; closed 0 (Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at real prices (options: issue-time ask to exit-session bid). Decision support only.

| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | Predicted central | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |
| OPTION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |
| QUOTE_CURRENT_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |
| QUOTE_PRIOR_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 97 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 1431 | 1124 | 947 | 678 | 516 | 353 | 359 | 269 | 219 | 180 | 231 | 204 | 184 | 152 | 132 | 145 | 153 | 119 | 79 | 58 |
| TARGET_FIRST | 359 | 196 | 135 | 110 | 62 | 38 | 31 | 30 | 44 | 24 | 21 | 19 | 17 | 12 | 4 | 12 | 12 | 11 | 3 | 3 |

Caveats: 86 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
