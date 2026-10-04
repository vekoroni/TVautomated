# Outcome report — as of 2026-09-21

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 25069
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 924, THESIS_ID 14180
- **invalidation_state**: MISSING 3059, VALID 22010
- **target_state**: INVALID_LEGACY 7907, LEVEL 13587, NONE 3575
- **contract_state**: MISSING 5795, SIDE_MISMATCH 1361, VALID 17913
- **direction**: BEAR 6042, BULL 17748, None 1279
- **base_state**: NOT_SCORABLE 2733, NO_ATR 11, None 1543, OK 20782
- **macro_freshness**: CURRENT 24376, STALE 693
- **outcome_state**: AMBIGUOUS 166, DATA_GAP 19, NOT_SCORABLE 2733, NOT_YET_SCORED 1543, OPEN_CENSORED 7996, STOP_FIRST 8488, TARGET_FIRST 1277, TIMEOUT 2847

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 20782 | 22 | 6.9% / 8.2% / 9.7% | 8.1% | -0.3% / +0.1% / +0.5% | 56.3% / 60.3% / 63.7% | 58.3% | +1.4% / +2.1% / +2.7% | OK |
| headline | direction=BEAR | 5091 | 21 | 5.5% / 7.7% / 10.7% | 8.5% | -1.8% / -0.8% / +0.4% | 33.2% / 38.4% / 44.7% | 36.3% | +0.4% / +2.1% / +3.8% | OK |
| headline | direction=BULL | 15691 | 21 | 7.2% / 8.5% / 10.1% | 8.3% | -0.2% / +0.2% / +0.7% | 59.8% / 64.9% / 69.5% | 62.9% | +1.1% / +2.0% / +2.9% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 12.1% | -13.9% / -12.1% / -8.4% | 27.3% / 37.5% / 60.0% | 20.9% | +10.2% / +16.6% / +30.7% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 4.7% / 12.0% / 16.8% | 13.9% | -7.2% / -1.8% / +2.7% | 40.2% / 45.9% / 68.6% | 44.4% | -1.2% / +1.6% / +20.1% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 860 | 12 | 0.0% / 0.0% / 0.0% | 0.0% | -0.1% / -0.0% / -0.0% | 43.0% / 52.1% / 57.5% | 52.3% | -8.9% / -0.2% / +10.6% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 8744 | 11 | 5.4% / 12.3% / 17.9% | 13.2% | -1.5% / -1.0% / +1.2% | 35.5% / 46.0% / 50.8% | 41.8% | +1.0% / +4.2% / +5.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1830 | 10 | 4.2% / 15.3% / 27.4% | 14.3% | -1.3% / +0.9% / +5.2% | 39.7% / 45.3% / 52.5% | 43.8% | -5.2% / +1.5% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 4 | 2 | 0.0% / 37.5% / 37.5% | 27.1% | -2.8% / +10.4% / +10.4% | 0.0% / 62.5% / 66.7% | 69.8% | -18.3% / -7.3% / -4.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 95 | 6 | 0.0% / 8.7% / 29.3% | 11.1% | -5.5% / -2.4% / +14.5% | 11.9% / 28.7% / 46.5% | 50.1% | -23.6% / -21.5% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 911 | 9 | 0.0% / 0.0% / 0.0% | 2.2% | -4.8% / -2.2% / -0.0% | 37.9% / 62.9% / 68.9% | 48.8% | +3.5% / +14.1% / +15.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 8415 | 11 | 6.8% / 12.7% / 16.7% | 12.4% | -2.7% / +0.3% / +1.7% | 37.2% / 49.7% / 63.6% | 43.1% | +3.2% / +6.6% / +13.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2842 | 18 | 5.5% / 9.1% / 22.6% | 8.8% | -2.2% / +0.3% / +2.3% | 50.4% / 64.8% / 69.7% | 63.1% | -1.6% / +1.7% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 921 | 10 | 0.0% / 0.0% / 0.0% | 1.6% | -4.1% / -1.6% / -0.0% | 48.2% / 82.4% / 86.0% | 64.7% | +8.7% / +17.6% / +18.9% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 4 | 2 | 0.0% / 37.5% / 37.5% | 27.1% | -2.8% / +10.4% / +10.4% | 0.0% / 62.5% / 66.7% | 69.8% | -18.3% / -7.3% / -4.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 120 | 7 | 0.0% / 11.4% / 21.6% | 18.7% | -11.6% / -7.3% / +8.1% | 20.5% / 56.5% / 59.9% | 44.8% | -22.1% / +11.7% / +20.6% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 8415 | 11 | 6.8% / 12.7% / 16.7% | 12.4% | -2.7% / +0.3% / +1.7% | 37.2% / 49.7% / 63.6% | 43.1% | +3.2% / +6.6% / +13.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.3% / 65.0% / 68.6% | 63.1% | +1.2% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 12281 | 20 | 18.8% / 21.7% / 26.2% | 21.1% | -0.4% / +0.5% / +1.6% | 52.8% / 55.2% / 57.1% | 53.0% | +0.8% / +2.2% / +3.3% | OK |
| headline | target_state=NONE | 943 | 8 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 28.8% / 44.5% / 49.9% | 40.8% | -4.3% / +3.7% / +6.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 2997 | 7 | 2.0% / 7.3% / 11.4% | 12.5% | -7.2% / -5.2% / -1.4% | 32.4% / 69.2% / 73.1% | 52.3% | +4.1% / +16.9% / +17.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 119 | 7 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.0% / 36.0% / 52.0% | 37.2% | -5.8% / -1.2% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 61 | 6 | 0.0% / 0.0% / 0.0% | 25.4% | -31.1% / -25.4% / -19.4% | 100.0% / 100.0% / 100.0% | 73.6% | +20.5% / +26.4% / +32.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 25.0% / 25.0% / 25.0% | 30.4% | -5.4% / -5.4% / -5.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 55 | 6 | 75.0% / 87.3% / 92.3% | 33.5% | +45.7% / +53.8% / +63.6% | 7.7% / 12.7% / 25.0% | 66.1% | -62.4% / -53.4% / -44.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 12 | 6 | 0.0% / 0.0% / 0.0% | 1.5% | -3.9% / -1.5% / +0.0% | 12.5% / 63.3% / 100.0% | 28.5% | -8.0% / +34.9% / +71.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 13 | 3 | 0.0% / 15.4% / 33.3% | 5.4% | -0.8% / +10.0% / +23.4% | 7.7% / 15.4% / 23.1% | 21.0% | -17.4% / -5.7% / +8.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 5854 | 9 | 6.4% / 8.9% / 15.2% | 11.8% | -3.5% / -2.8% / +1.3% | 37.2% / 41.8% / 45.6% | 44.3% | -5.8% / -2.4% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 2107 | 9 | 6.8% / 16.9% / 24.0% | 14.3% | -0.1% / +2.6% / +6.0% | 35.4% / 47.0% / 49.0% | 35.5% | +4.6% / +11.6% / +12.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 5 | 2 | 25.0% / 40.0% / 100.0% | 27.6% | +12.4% / +12.4% / +41.5% | 0.0% / 0.0% / 0.0% | 58.4% | -58.4% / -58.4% / -34.4% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 2.5% / 2.5% / 2.5% | 4.8% | -2.3% / -2.3% / -2.3% | 40.9% / 40.9% / 40.9% | 34.6% | +6.3% / +6.3% / +6.3% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.0% / 2.0% / 2.0% | 5.3% | -3.3% / -3.3% / -3.3% | 29.6% / 29.6% / 29.6% | 26.1% | +3.5% / +3.5% / +3.5% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 1.7% | -0.5% / -0.5% / -0.5% | 22.0% / 22.0% / 22.0% | 19.8% | +2.2% / +2.2% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 1856 | 9 | 7.4% / 10.0% / 17.0% | 13.4% | -5.1% / -3.4% / +3.5% | 29.0% / 54.5% / 57.2% | 44.4% | -9.5% / +10.2% / +11.9% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 1737 | 10 | 8.5% / 18.4% / 23.1% | 16.8% | -0.8% / +1.5% / +3.0% | 35.6% / 46.6% / 51.0% | 45.5% | -3.5% / +1.0% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 4822 | 10 | 5.1% / 12.2% / 17.7% | 12.3% | -1.8% / -0.1% / +2.6% | 37.6% / 47.8% / 53.9% | 41.2% | +2.9% / +6.6% / +8.9% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 1735 | 12 | 2.9% / 4.8% / 9.6% | 6.2% | -2.1% / -1.5% / +1.0% | 31.9% / 39.4% / 48.5% | 40.5% | -6.8% / -1.1% / +8.5% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 3742 | 18 | 5.6% / 8.4% / 12.0% | 9.4% | -2.1% / -1.0% / +0.5% | 33.2% / 38.7% / 45.7% | 36.8% | +0.1% / +2.0% / +3.8% | INSUFFICIENT_SESSIONS |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 1.5% / 3.1% / 3.5% | 3.4% | -0.9% / -0.4% / +0.3% | 13.9% / 45.5% / 59.8% | 43.1% | -0.3% / +2.4% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 12745 | 18 | 6.3% / 7.6% / 9.1% | 7.4% | -0.3% / +0.2% / +0.7% | 62.5% / 67.3% / 71.4% | 65.2% | +1.1% / +2.1% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 9.1% / 12.3% / 14.1% | 12.1% | -0.7% / +0.2% / +1.0% | 37.1% / 48.7% / 50.1% | 47.8% | -1.5% / +0.8% / +1.9% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 20109 | 21 | 6.7% / 7.8% / 9.1% | 7.8% | -0.4% / +0.0% / +0.5% | 56.4% / 60.6% / 64.0% | 58.6% | +1.2% / +2.0% / +2.6% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 7.2% / 16.1% / 24.9% | 15.9% | +0.2% / +0.2% / +1.9% | 38.8% / 47.7% / 50.3% | 42.1% | +3.6% / +5.6% / +5.6% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 9824 | 7 | 2.9% / 4.6% / 5.8% | 5.1% | -1.2% / -0.5% / +0.3% | 25.7% / 31.3% / 32.5% | 31.7% | -5.3% / -0.4% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.5% / 10.0% / 13.1% | 9.2% | -0.1% / +0.7% / +1.7% | 52.1% / 59.3% / 65.0% | 57.5% | +0.4% / +1.8% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 16487 | 19 | 6.4% / 7.6% / 9.4% | 7.6% | -0.5% / +0.0% / +0.6% | 58.9% / 62.5% / 65.3% | 60.4% | +1.3% / +2.1% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 6.3% / 9.6% / 12.1% | 9.6% | -0.4% / +0.0% / +0.8% | 28.9% / 45.7% / 47.8% | 44.6% | -0.6% / +1.1% / +2.0% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 11256 | 13 | 5.8% / 11.5% / 16.4% | 12.3% | -1.2% / -0.8% / +0.8% | 38.1% / 47.1% / 51.3% | 42.3% | -2.3% / +4.8% / +6.6% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.9% | -0.5% / +0.2% / +1.1% | 55.9% / 62.1% / 67.5% | 60.3% | +0.7% / +1.8% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 8429 | 9 | 5.1% / 7.8% / 9.5% | 8.0% | -1.0% / -0.2% / +0.4% | 36.8% / 57.8% / 66.4% | 55.0% | +1.0% / +2.8% / +4.9% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 10215 | 12 | 6.9% / 8.5% / 11.4% | 8.1% | -0.1% / +0.4% / +1.3% | 55.5% / 60.3% / 63.7% | 59.1% | +0.3% / +1.2% / +2.0% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 20782 | 22 | 6.9% / 8.2% / 9.7% | 8.1% | -0.3% / +0.1% / +0.5% | 56.3% / 60.3% / 63.7% | 58.3% | +1.4% / +2.1% / +2.7% | OK |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 4008, MARK_UNAVAILABLE 2366
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 531, RESOLUTION 3265, TIMEOUT 212

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 4008 | 20 | 14% | -60.0% | -49.4% / -44.7% / -38.4% | -1.6% | OK |
| direction=BEAR | 882 | 20 | 25% | -48.0% | -33.9% / -23.5% / -13.1% | -2.4% | OK |
| direction=BULL | 3126 | 20 | 11% | -62.1% | -55.4% / -50.7% / -45.1% | -1.5% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 3786 | 20 | 14% | -59.4% | -49.7% / -44.9% / -38.1% | -1.7% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 531 | 10 | 25% | -76.5% | -46.2% / -38.7% / -29.9% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 3265 | 20 | 11% | -59.5% | -52.7% / -47.9% / -41.5% | -2.2% | OK |
| exit_reason=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 989 | 16 | 12% | -63.7% | -57.4% / -49.3% / -33.1% | -2.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0% | -85.8% | -97.6% / -82.9% / -76.6% | -3.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 35 | 6 | 29% | -44.6% | -47.5% / -15.0% / +3.3% | -3.3% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 2264 | 10 | 12% | -57.4% | -52.5% / -47.8% / -41.6% | -2.0% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 257 | 10 | 20% | -71.4% | -48.6% / -42.1% / -38.8% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 3728 | 20 | 13% | -59.4% | -49.9% / -45.0% / -38.0% | -1.7% | OK |
| target_state=NONE | 23 | 3 | 30% | -85.7% | -91.5% / -39.1% / -29.7% | n/a | INSUFFICIENT_SESSIONS |
| tier=0 | 220 | 1 | 4% | -64.9% | -60.3% / -60.3% / -60.3% | -2.8% | INSUFFICIENT_SESSIONS |
| tier=1 | 72 | 1 | 6% | -71.3% | -62.4% / -62.4% / -62.4% | -5.8% | INSUFFICIENT_SESSIONS |
| tier=2 | 70 | 1 | 1% | -73.3% | -73.2% / -73.2% / -73.2% | -3.3% | INSUFFICIENT_SESSIONS |
| tier=A | 523 | 9 | 13% | -47.8% | -46.6% / -37.9% / -26.4% | -2.4% | INSUFFICIENT_SESSIONS |
| tier=B | 718 | 10 | 18% | -51.7% | -48.5% / -39.2% / -30.2% | -1.8% | INSUFFICIENT_SESSIONS |
| tier=C | 1332 | 10 | 9% | -61.6% | -57.1% / -52.1% / -45.7% | -2.0% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 226 | 10 | 9% | -68.7% | -63.4% / -56.7% / -51.0% | -1.5% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 156 | 12 | 8% | -36.6% | -47.0% / -39.9% / -33.7% | -0.7% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 94 | 6 | 24% | -52.1% | -65.9% / -33.1% / -19.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 437 | 10 | 25% | -80.6% | -48.6% / -39.9% / -30.0% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 2450 | 20 | 0% | -68.8% | -72.0% / -66.2% / -60.7% | -4.3% | OK |
| underlying_state=TARGET_FIRST | 659 | 20 | 51% | +2.9% | +7.9% / +18.4% / +31.9% | +5.6% | OK |
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

Candidates considered 1499; tickets issued 5; closed 3 (Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at real prices (options: issue-time ask to exit-session bid). Decision support only.

| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | Predicted central | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 3 | 1 | 0% | -38.3% | n/a | n/a | -38.3% | -65.1% | 81.0% | +6.4% | INSUFFICIENT_EVIDENCE |
| OPTION | 3 | 1 | 0% | -38.3% | n/a | n/a | -38.3% | -65.1% | 81.0% | +6.4% | INSUFFICIENT_EVIDENCE |
| QUOTE_CURRENT_SESSION | 3 | 1 | 0% | -38.3% | n/a | n/a | -38.3% | -65.1% | 81.0% | +6.4% | INSUFFICIENT_EVIDENCE |
| QUOTE_PRIOR_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 164 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 1888 | 1301 | 982 | 715 | 582 | 430 | 398 | 274 | 233 | 188 | 238 | 208 | 188 | 154 | 132 | 145 | 153 | 119 | 88 | 72 |
| TARGET_FIRST | 419 | 213 | 156 | 117 | 71 | 40 | 39 | 30 | 44 | 25 | 26 | 20 | 19 | 12 | 4 | 12 | 12 | 11 | 3 | 4 |

Caveats: 86 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
