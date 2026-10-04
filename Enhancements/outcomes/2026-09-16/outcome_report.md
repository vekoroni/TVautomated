# Outcome report — as of 2026-09-16

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `8f9bd38e1be7d6b6` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 18330
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 426, THESIS_ID 7939
- **invalidation_state**: MISSING 1830, VALID 16500
- **target_state**: INVALID_LEGACY 7728, LEVEL 8977, NONE 1625
- **contract_state**: MISSING 4451, SIDE_MISMATCH 1361, VALID 12518
- **direction**: BEAR 4170, BULL 13369, None 791
- **base_state**: NOT_SCORABLE 1528, NO_ATR 11, None 1476, OK 15315
- **macro_freshness**: CURRENT 17637, STALE 693
- **outcome_state**: AMBIGUOUS 79, DATA_GAP 21, NOT_SCORABLE 1528, NOT_YET_SCORED 1476, OPEN_CENSORED 4479, STOP_FIRST 7376, TARGET_FIRST 1087, TIMEOUT 2284

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 15315 | 19 | 7.0% / 8.4% / 10.0% | 8.1% | -0.2% / +0.3% / +0.8% | 57.7% / 61.7% / 65.1% | 59.6% | +1.4% / +2.1% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR | 3421 | 18 | 5.6% / 8.2% / 11.8% | 8.8% | -1.7% / -0.6% / +0.9% | 33.9% / 39.9% / 47.7% | 39.1% | -0.9% / +0.8% / +2.4% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL | 11894 | 18 | 7.1% / 8.7% / 10.3% | 8.2% | -0.0% / +0.5% / +1.0% | 60.6% / 65.8% / 70.4% | 63.5% | +1.4% / +2.2% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 9.1% | -11.4% / -9.1% / -5.7% | 27.3% / 37.5% / 60.0% | 17.7% | +12.4% / +19.8% / +36.0% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 853 | 7 | 4.6% / 11.8% / 18.6% | 12.8% | -5.9% / -1.0% / +3.5% | 34.6% / 42.4% / 55.4% | 49.6% | -17.5% / -7.2% / +9.0% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 150 | 9 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 38.9% / 50.4% / 58.0% | 53.9% | -11.5% / -3.5% / +8.3% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 4778 | 8 | 5.9% / 15.4% / 19.8% | 14.0% | +0.1% / +1.4% / +3.2% | 37.4% / 49.7% / 53.1% | 45.0% | +2.2% / +4.7% / +6.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1791 | 7 | 4.1% / 19.6% / 27.1% | 16.1% | -0.5% / +3.4% / +5.8% | 39.4% / 45.2% / 56.3% | 43.4% | -2.7% / +1.8% / +6.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.2% | +8.1% / +8.1% / +8.1% | 66.7% / 66.7% / 66.7% | 69.9% | -3.3% / -3.3% / -3.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 33 | 3 | 0.0% / 9.1% / 25.0% | 10.7% | -4.8% / -1.6% / +11.2% | 16.7% / 59.1% / 62.9% | 54.2% | -5.9% / +4.9% / +7.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 140 | 6 | 0.0% / 0.0% / 0.0% | 2.5% | -5.2% / -2.5% / +0.0% | 29.6% / 49.7% / 62.6% | 50.4% | -6.1% / -0.7% / +14.0% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 3821 | 8 | 6.4% / 10.1% / 16.7% | 11.6% | -1.7% / -1.4% / +2.0% | 37.2% / 59.9% / 62.5% | 49.0% | +3.8% / +10.8% / +11.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2803 | 15 | 5.3% / 9.2% / 25.5% | 9.1% | -1.0% / +0.0% / +4.0% | 51.1% / 67.2% / 71.1% | 65.9% | -2.5% / +1.2% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 150 | 7 | 0.0% / 0.0% / 0.0% | 1.9% | -4.5% / -1.9% / +0.0% | 39.4% / 84.5% / 88.1% | 67.1% | -4.2% / +17.3% / +22.7% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 3 | 1 | 33.3% / 33.3% / 33.3% | 25.2% | +8.1% / +8.1% / +8.1% | 66.7% / 66.7% / 66.7% | 69.9% | -3.3% / -3.3% / -3.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 58 | 4 | 0.0% / 13.9% / 21.4% | 17.7% | -6.5% / -3.8% / +5.1% | 19.4% / 54.5% / 60.6% | 44.6% | -1.0% / +10.0% / +14.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 3821 | 8 | 6.4% / 10.1% / 16.7% | 11.6% | -1.7% / -1.4% / +2.0% | 37.2% / 59.9% / 62.5% | 49.0% | +3.8% / +10.8% / +11.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.3% / +0.2% / +0.8% | 57.0% / 61.4% / 64.8% | 59.6% | +0.8% / +1.8% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7497 | 18 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.7% / 65.4% / 69.2% | 63.3% | +1.2% / +2.1% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 7740 | 17 | 21.4% / 24.6% / 29.8% | 23.8% | -0.3% / +0.9% / +2.5% | 53.1% / 56.8% / 59.0% | 54.6% | +0.7% / +2.2% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | target_state=NONE | 78 | 5 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 17.8% / 32.3% / 44.4% | 40.7% | -15.8% / -8.4% / +3.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 2287 | 4 | 2.2% / 7.1% / 15.0% | 11.6% | -4.5% / -4.5% / -0.4% | 29.6% / 68.5% / 71.2% | 57.8% | +4.0% / +10.7% / +10.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 97 | 4 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.0% / 44.6% / 58.2% | 44.3% | -5.2% / +0.4% / +7.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 32 | 3 | 0.0% / 0.0% / 0.0% | 29.1% | -31.2% / -29.1% / -23.2% | 100.0% / 100.0% / 100.0% | 69.6% | +24.7% / +30.4% / +32.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 18.8% / 18.8% / 18.8% | 24.6% | -5.9% / -5.9% / -5.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 45 | 3 | 88.2% / 88.9% / 100.0% | 34.2% | +53.6% / +54.7% / +78.5% | 0.0% / 11.1% / 11.8% | 65.0% | -73.5% / -53.9% / -52.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 4 | 3 | 0.0% / 0.0% / 0.0% | 0.6% | -1.2% / -0.6% / +0.0% | 0.0% / 0.0% / 0.0% | 24.5% | -36.7% / -24.5% / -11.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 13 | 3 | 0.0% / 15.4% / 33.3% | 5.2% | -0.6% / +10.2% / +23.9% | 7.7% / 15.4% / 23.1% | 19.5% | -14.7% / -4.2% / +9.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 2387 | 6 | 7.4% / 13.4% / 19.7% | 11.8% | +0.7% / +1.6% / +5.0% | 39.5% / 48.6% / 50.7% | 48.2% | -4.0% / +0.4% / +5.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 886 | 6 | 6.0% / 19.8% / 25.8% | 16.8% | -0.7% / +2.9% / +7.3% | 31.7% / 39.3% / 44.6% | 33.4% | +2.0% / +5.9% / +9.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 5 | 2 | 0.0% / 20.0% / 100.0% | 28.5% | -8.5% / -8.5% / +42.4% | 0.0% / 0.0% / 0.0% | 62.0% | -62.0% / -62.0% / -27.3% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 1.9% / 1.9% / 1.9% | 3.7% | -1.8% / -1.8% / -1.8% | 33.8% / 33.8% / 33.8% | 28.0% | +5.9% / +5.9% / +5.9% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.0% / 2.0% / 2.0% | 4.0% | -2.0% / -2.0% / -2.0% | 17.4% / 17.4% / 17.4% | 20.1% | -2.7% / -2.7% / -2.7% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 1.2% | +0.1% / +0.1% / +0.1% | 16.8% / 16.8% / 16.8% | 14.4% | +2.4% / +2.4% / +2.4% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 729 | 6 | 7.6% / 17.6% / 23.4% | 14.2% | -0.1% / +3.4% / +8.2% | 22.3% / 34.0% / 46.3% | 47.5% | -22.0% / -13.5% / -2.5% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 957 | 7 | 6.6% / 18.7% / 23.9% | 18.4% | -0.9% / +0.3% / +2.8% | 29.2% / 42.4% / 49.5% | 46.5% | -8.9% / -4.1% / -0.5% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 2416 | 7 | 5.4% / 13.9% / 19.7% | 12.6% | -0.9% / +1.4% / +5.3% | 40.2% / 55.9% / 58.6% | 44.3% | +6.7% / +11.6% / +11.8% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 581 | 9 | 5.7% / 11.2% / 15.7% | 7.3% | +1.6% / +3.9% / +6.5% | 40.6% / 50.1% / 56.3% | 44.4% | -2.2% / +5.7% / +11.2% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 2500 | 16 | 5.7% / 8.7% / 12.5% | 9.4% | -1.9% / -0.7% / +0.9% | 33.8% / 40.1% / 48.2% | 39.0% | -0.9% / +1.1% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 921 | 2 | 0.8% / 3.3% / 4.8% | 3.7% | -0.4% / -0.4% / +0.7% | 7.8% / 52.9% / 63.2% | 53.4% | -3.4% / -0.6% / -0.6% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 9763 | 16 | 6.4% / 7.7% / 9.3% | 7.4% | -0.2% / +0.3% / +1.0% | 63.0% / 67.8% / 72.1% | 65.5% | +1.3% / +2.2% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2131 | 2 | 9.1% / 13.1% / 14.9% | 12.3% | +0.8% / +0.8% / +1.5% | 34.3% / 50.2% / 50.2% | 49.1% | +1.1% / +1.1% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 14642 | 18 | 6.8% / 8.0% / 9.4% | 7.8% | -0.3% / +0.2% / +0.7% | 57.9% / 61.9% / 65.4% | 59.9% | +1.2% / +2.0% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=STALE | 673 | 3 | 6.7% / 18.0% / 24.2% | 15.7% | +0.4% / +2.2% / +5.6% | 34.3% / 44.3% / 47.5% | 41.0% | +0.4% / +3.3% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.7% / 66.1% | 62.0% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 4357 | 4 | 1.7% / 4.0% / 5.9% | 4.2% | -1.3% / -0.2% / +0.4% | 22.1% / 27.8% / 28.7% | 26.9% | -6.5% / +0.9% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.5% / 9.9% / 13.1% | 9.1% | +0.0% / +0.9% / +1.9% | 52.4% / 59.8% / 65.5% | 57.8% | +0.5% / +2.0% / +3.3% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 12263 | 17 | 6.5% / 7.8% / 9.8% | 7.7% | -0.3% / +0.2% / +0.8% | 59.9% / 63.4% / 66.4% | 61.3% | +1.4% / +2.2% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_LONG_ONLY | 3052 | 2 | 5.9% / 10.5% / 13.6% | 10.1% | +0.4% / +0.4% / +1.4% | 24.3% / 48.2% / 49.3% | 47.8% | +0.4% / +0.4% / +1.6% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.3% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 5789 | 10 | 6.0% / 14.0% / 18.5% | 13.1% | -0.2% / +0.9% / +2.8% | 41.3% / 50.0% / 53.3% | 45.3% | +1.4% / +4.7% / +9.0% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.8% | -0.5% / +0.3% / +1.1% | 55.9% / 62.2% / 67.5% | 60.2% | +0.8% / +2.0% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 3.9% / 7.1% / 9.7% | 7.6% | -1.2% / -0.5% / +0.1% | 65.1% / 68.2% / 71.8% | 65.6% | +2.5% / +2.6% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 6673 | 7 | 4.6% / 7.9% / 10.0% | 7.8% | -0.6% / +0.1% / +0.6% | 34.3% / 60.4% / 67.8% | 57.5% | +0.7% / +2.8% / +4.6% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 6504 | 10 | 7.2% / 9.0% / 12.1% | 8.3% | +0.0% / +0.7% / +1.9% | 54.7% / 60.2% / 63.8% | 59.1% | +0.1% / +1.1% / +2.0% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 15315 | 19 | 7.0% / 8.4% / 10.0% | 8.1% | -0.2% / +0.3% / +0.8% | 57.7% / 61.7% / 65.1% | 59.6% | +1.4% / +2.1% / +2.8% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1409, ENTRY_NOT_VALUED 1845, MARKED 2937, MARK_UNAVAILABLE 2285
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 531, RESOLUTION 2195, TIMEOUT 211

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 2937 | 17 | 16% | -64.0% | -49.8% / -45.0% / -38.5% | -1.3% | INSUFFICIENT_SESSIONS |
| direction=BEAR | 660 | 17 | 31% | -44.4% | -23.0% / -13.9% / -5.2% | +0.2% | INSUFFICIENT_SESSIONS |
| direction=BULL | 2277 | 17 | 11% | -67.8% | -58.5% / -54.0% / -48.6% | -1.6% | INSUFFICIENT_SESSIONS |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 2715 | 17 | 15% | -63.2% | -50.4% / -45.3% / -38.0% | -1.4% | INSUFFICIENT_SESSIONS |
| exit_reason=CONTRACT_LAST_USABLE | 531 | 10 | 25% | -76.5% | -46.2% / -38.7% / -29.9% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 2195 | 17 | 12% | -63.8% | -54.5% / -49.8% / -43.2% | -2.1% | INSUFFICIENT_SESSIONS |
| exit_reason=TIMEOUT | 211 | 5 | 35% | -44.8% | -22.9% / -10.9% / -0.1% | +6.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 853 | 13 | 13% | -63.2% | -57.3% / -48.4% / -32.7% | -2.0% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0% | -85.8% | -97.6% / -82.9% / -76.6% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 29 | 4 | 34% | -51.1% | -55.5% / -10.5% / +6.2% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 1335 | 7 | 13% | -65.0% | -55.8% / -51.5% / -44.7% | -2.0% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 257 | 10 | 20% | -71.4% | -48.6% / -42.1% / -38.8% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 2657 | 17 | 15% | -63.2% | -50.5% / -45.3% / -38.0% | -1.4% | INSUFFICIENT_SESSIONS |
| target_state=NONE | 23 | 3 | 30% | -85.7% | -91.5% / -39.1% / -29.7% | n/a | INSUFFICIENT_SESSIONS |
| tier=0 | 182 | 1 | 3% | -63.5% | -60.7% / -60.7% / -60.7% | -2.8% | INSUFFICIENT_SESSIONS |
| tier=1 | 47 | 1 | 9% | -62.1% | -54.2% / -54.2% / -54.2% | -2.5% | INSUFFICIENT_SESSIONS |
| tier=2 | 54 | 1 | 2% | -74.4% | -72.8% / -72.8% / -72.8% | -2.8% | INSUFFICIENT_SESSIONS |
| tier=A | 254 | 6 | 13% | -58.2% | -49.0% / -44.3% / -32.6% | -2.3% | INSUFFICIENT_SESSIONS |
| tier=B | 503 | 7 | 19% | -57.9% | -54.4% / -40.4% / -28.9% | -1.8% | INSUFFICIENT_SESSIONS |
| tier=C | 879 | 7 | 11% | -66.7% | -59.5% / -53.6% / -47.3% | -2.0% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 172 | 7 | 12% | -75.0% | -65.4% / -56.7% / -50.7% | -1.3% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 73 | 9 | 3% | -44.0% | -52.1% / -48.3% / -39.7% | -0.8% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 94 | 6 | 24% | -52.1% | -65.9% / -33.1% / -19.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 437 | 10 | 25% | -80.6% | -48.6% / -39.9% / -30.0% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 1631 | 17 | 0% | -73.7% | -76.5% / -70.2% / -66.7% | -4.5% | INSUFFICIENT_SESSIONS |
| underlying_state=TARGET_FIRST | 491 | 17 | 50% | +0.9% | +1.9% / +17.8% / +36.6% | +5.6% | INSUFFICIENT_SESSIONS |
| underlying_state=TIMEOUT | 211 | 5 | 35% | -44.8% | -22.9% / -10.9% / -0.1% | +6.5% | INSUFFICIENT_SESSIONS |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 77 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 1367 | 1124 | 922 | 657 | 486 | 353 | 357 | 268 | 218 | 180 | 231 | 203 | 184 | 152 | 132 | 145 | 153 | 114 | 72 | 58 |
| TARGET_FIRST | 323 | 196 | 129 | 108 | 56 | 38 | 31 | 30 | 42 | 23 | 21 | 17 | 17 | 12 | 4 | 12 | 12 | 10 | 3 | 3 |

Caveats: 86 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
