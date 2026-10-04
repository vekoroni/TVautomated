# Outcome report — as of 2026-10-01

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 36650, RETROSPECTIVE_UNVERIFIED 763
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 2153, THESIS_ID 25295
- **invalidation_state**: MISSING 5479, VALID 31934
- **target_state**: INVALID_LEGACY 8452, LEVEL 23228, NONE 5733
- **contract_state**: MISSING 7076, SIDE_MISMATCH 1361, VALID 28976
- **direction**: BEAR 9071, BULL 25849, None 2493
- **base_state**: NOT_SCORABLE 5134, NO_ATR 12, None 1554, OK 30713
- **macro_freshness**: CURRENT 36720, STALE 693
- **outcome_state**: AMBIGUOUS 424, DATA_GAP 27, NOT_SCORABLE 5134, NOT_YET_SCORED 1554, OPEN_CENSORED 11839, STOP_FIRST 13594, TARGET_FIRST 1913, TIMEOUT 2928

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 30007 | 28 | 6.7% / 7.7% / 8.9% | 8.0% | -0.6% / -0.3% / +0.1% | 54.9% / 58.3% / 61.5% | 56.4% | +1.4% / +1.9% / +2.4% | OK |
| headline | direction=BEAR | 7562 | 27 | 6.9% / 8.6% / 10.9% | 10.1% | -2.4% / -1.5% / -0.7% | 23.3% / 27.2% / 33.2% | 26.7% | -0.6% / +0.5% / +1.9% | OK |
| headline | direction=BULL | 22445 | 27 | 6.5% / 7.7% / 9.0% | 7.6% | -0.3% / +0.0% / +0.4% | 62.7% / 66.4% / 69.9% | 64.4% | +1.3% / +2.0% / +2.7% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 9 | 4 | 0.0% / 0.0% / 0.0% | 16.8% | -19.6% / -16.8% / -7.3% | 25.0% / 49.2% / 77.8% | 35.0% | -5.1% / +14.3% / +39.1% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 2121 | 10 | 8.8% / 11.2% / 15.4% | 12.7% | -2.7% / -1.5% / +0.1% | 48.9% / 56.2% / 59.9% | 51.4% | -5.4% / +4.8% / +9.9% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 919 | 18 | 0.0% / 0.0% / 0.0% | 0.4% | -0.8% / -0.4% / -0.2% | 49.5% / 60.4% / 76.9% | 56.6% | -4.7% / +3.8% / +18.8% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 17432 | 17 | 6.6% / 9.2% / 13.2% | 10.7% | -2.2% / -1.5% / -0.3% | 51.2% / 54.8% / 57.9% | 50.4% | +2.2% / +4.4% / +5.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1938 | 14 | 6.0% / 13.4% / 25.2% | 14.2% | -2.4% / -0.8% / +2.9% | 53.2% / 59.5% / 75.6% | 51.3% | +1.3% / +8.1% / +20.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 10 | 4 | 0.0% / 10.0% / 25.0% | 20.5% | -16.0% / -10.5% / -0.4% | 60.0% / 75.0% / 100.0% | 77.1% | -12.8% / -2.1% / +30.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 347 | 10 | 1.6% / 3.5% / 5.5% | 8.1% | -7.7% / -4.6% / -0.2% | 30.6% / 38.7% / 65.3% | 57.1% | -21.3% / -18.4% / -0.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 988 | 15 | 0.0% / 0.0% / 0.0% | 0.9% | -3.2% / -0.9% / -0.3% | 36.6% / 52.7% / 60.1% | 51.6% | -4.9% / +1.1% / +8.3% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 17197 | 17 | 7.2% / 8.3% / 9.6% | 10.3% | -3.6% / -2.0% / -1.0% | 50.4% / 54.6% / 57.4% | 50.8% | -3.1% / +3.8% / +5.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 3037 | 22 | 5.8% / 9.2% / 19.6% | 9.7% | -2.7% / -0.5% / +1.6% | 54.1% / 61.6% / 69.0% | 58.8% | +0.8% / +2.7% / +5.8% | OK |
| headline | lab_verdict=CONTRACT_REPAIR | 998 | 16 | 0.0% / 0.0% / 0.0% | 0.8% | -2.8% / -0.8% / -0.3% | 41.4% / 54.7% / 64.2% | 52.8% | -3.2% / +1.8% / +10.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 6 | 3 | 0.0% / 16.7% / 28.6% | 23.1% | -15.3% / -6.5% / +2.6% | 57.1% / 66.7% / 80.0% | 74.7% | -18.2% / -8.1% / +21.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 291 | 10 | 2.2% / 5.1% / 8.2% | 12.6% | -10.0% / -7.5% / -1.1% | 31.3% / 51.8% / 63.0% | 47.9% | -19.7% / +4.0% / +13.9% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 17195 | 17 | 7.2% / 8.3% / 9.6% | 10.3% | -3.6% / -2.0% / -1.0% | 50.4% / 54.6% / 57.4% | 50.8% | -3.1% / +3.8% / +5.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 59.4% / 64.2% / 67.9% | 62.3% | +1.3% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 21222 | 26 | 11.6% / 13.8% / 17.0% | 14.4% | -1.2% / -0.6% / +0.2% | 52.9% / 55.0% / 57.5% | 53.3% | +0.7% / +1.7% / +2.9% | OK |
| headline | target_state=NONE | 1227 | 14 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 20.9% / 40.7% / 51.5% | 44.3% | -7.7% / -3.6% / +8.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 4499 | 11 | 5.1% / 6.5% / 8.3% | 11.5% | -7.1% / -5.0% / -0.7% | 44.9% / 49.7% / 74.0% | 54.0% | -12.1% / -4.3% / +13.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 154 | 11 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.8% / 60.8% / 75.5% | 33.9% | -2.7% / +26.9% / +32.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 142 | 10 | 0.0% / 0.0% / 0.0% | 19.4% | -24.6% / -19.4% / -14.8% | 100.0% / 100.0% / 100.0% | 80.1% | +16.1% / +19.9% / +25.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.3% | -0.3% / -0.3% / -0.3% | 34.4% / 34.4% / 34.4% | 43.9% | -9.5% / -9.5% / -9.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 81 | 10 | 51.5% / 76.5% / 84.9% | 29.5% | +30.2% / +47.0% / +53.3% | 15.1% / 23.5% / 48.5% | 70.4% | -53.1% / -46.9% / -29.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 30 | 12 | 0.0% / 0.0% / 0.0% | 1.3% | -5.2% / -1.3% / +0.0% | 9.1% / 21.2% / 35.6% | 30.9% | -26.7% / -9.7% / +3.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 122 | 9 | 0.0% / 10.8% / 38.8% | 4.9% | -3.0% / +5.8% / +31.8% | 20.8% / 37.2% / 45.3% | 47.7% | -28.5% / -10.4% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 10258 | 15 | 6.4% / 8.7% / 13.0% | 9.7% | -1.9% / -0.9% / +1.6% | 54.7% / 59.6% / 62.0% | 55.1% | -0.5% / +4.5% / +6.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 4811 | 15 | 8.4% / 10.6% / 15.1% | 12.9% | -4.1% / -2.2% / -0.7% | 39.1% / 44.2% / 52.1% | 41.5% | -1.8% / +2.7% / +10.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 351 | 8 | 2.2% / 3.9% / 7.3% | 14.4% | -17.7% / -10.5% / -0.4% | 36.3% / 44.3% / 47.6% | 65.2% | -32.4% / -20.9% / +2.3% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 4.2% / 4.2% / 4.2% | 6.9% | -2.7% / -2.7% / -2.7% | 52.9% / 52.9% / 52.9% | 47.9% | +4.9% / +4.9% / +4.9% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 5.9% / 5.9% / 5.9% | 9.5% | -3.6% / -3.6% / -3.6% | 38.7% / 38.7% / 38.7% | 38.0% | +0.7% / +0.7% / +0.7% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 2.8% / 2.8% / 2.8% | 3.5% | -0.7% / -0.7% / -0.7% | 39.4% / 39.4% / 39.4% | 34.4% | +5.0% / +5.0% / +5.0% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 5459 | 15 | 9.9% / 12.1% / 16.1% | 11.8% | -1.0% / +0.3% / +2.7% | 42.2% / 45.3% / 47.6% | 55.1% | -12.4% / -9.8% / -6.6% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 3370 | 16 | 9.0% / 12.7% / 16.7% | 14.3% | -3.3% / -1.6% / +0.8% | 47.9% / 52.4% / 89.9% | 54.3% | -4.5% / -1.9% / +33.0% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 8278 | 16 | 5.8% / 7.9% / 14.6% | 10.2% | -3.2% / -2.2% / +2.5% | 55.3% / 59.7% / 70.8% | 49.8% | +7.8% / +9.9% / +18.3% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 2268 | 18 | 2.0% / 3.7% / 6.9% | 5.7% | -3.5% / -2.0% / -0.4% | 39.9% / 49.4% / 69.9% | 44.5% | -0.7% / +4.9% / +25.2% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 130 | 2 | 0.0% / 5.1% / 6.0% | 4.7% | -2.4% / +0.5% / +1.3% | 4.8% / 6.2% / 6.4% | 6.2% | -2.0% / +0.0% / +3.9% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 576 | 2 | 1.4% / 2.2% / 2.8% | 2.9% | -0.7% / -0.7% / -0.4% | 31.7% / 50.7% / 51.0% | 47.8% | +1.8% / +2.9% / +2.9% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 107 | 2 | 10.1% / 11.2% / 13.2% | 12.0% | -0.8% / -0.8% / +4.9% | 86.8% / 88.8% / 89.9% | 82.3% | -2.6% / +6.5% / +29.4% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 5 | 2 | 0.0% / 0.0% / 0.0% | 1.4% | -2.1% / -1.4% / -0.2% | 0.0% / 20.0% / 33.3% | 26.8% | -6.8% / -6.8% / -3.6% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 96 | 2 | 0.0% / 4.0% / 4.0% | 2.1% | -1.5% / +1.9% / +2.0% | 10.6% / 32.5% / 43.3% | 37.8% | -5.3% / -5.3% / -0.3% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 15.4% | -5.4% / -5.4% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 488 | 2 | 0.5% / 1.2% / 1.2% | 2.2% | -1.2% / -1.0% / -0.9% | 12.4% / 33.6% / 35.1% | 32.9% | -5.7% / +0.7% / +2.2% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 107 | 2 | 10.1% / 11.2% / 13.2% | 12.0% | -0.8% / -0.8% / +4.9% | 86.8% / 88.8% / 89.9% | 82.3% | -2.6% / +6.5% / +29.4% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 15.4% | -5.4% / -5.4% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 5 | 2 | 0.0% / 0.0% / 0.0% | 1.4% | -2.1% / -1.4% / -0.2% | 0.0% / 20.0% / 33.3% | 26.8% | -6.8% / -6.8% / -3.6% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 96 | 2 | 0.0% / 4.0% / 4.0% | 2.1% | -1.5% / +1.9% / +2.0% | 10.6% / 32.5% / 43.3% | 37.8% | -5.3% / -5.3% / -0.3% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 488 | 2 | 0.5% / 1.2% / 1.2% | 2.2% | -1.2% / -1.0% / -0.9% | 12.4% / 33.6% / 35.1% | 32.9% | -5.7% / +0.7% / +2.2% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 697 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.6% / 42.0% / 42.0% | 39.7% | +1.4% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 9 | 2 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 0.0% / 11.1% / 33.3% | 15.9% | -4.8% / -4.8% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 589 | 2 | 0.4% / 1.4% / 1.4% | 2.2% | -1.3% / -0.8% / -0.7% | 12.2% / 33.5% / 35.6% | 33.2% | -5.2% / +0.3% / +1.9% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 15.4% | -5.4% / -5.4% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 91 | 2 | 0.0% / 2.2% / 3.2% | 11.7% | -9.5% / -9.5% / -5.4% | 96.8% / 97.8% / 100.0% | 82.2% | +10.1% / +15.6% / +35.5% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 16 | 2 | 50.0% / 62.5% / 83.3% | 14.8% | +38.2% / +47.7% / +74.0% | 16.7% / 37.5% / 50.0% | 83.8% | -46.3% / -46.3% / -34.6% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 319 | 2 | 3.4% / 4.6% / 4.6% | 3.8% | +0.1% / +0.8% / +0.8% | 22.7% / 40.4% / 44.0% | 42.2% | -1.8% / -1.8% / -1.0% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 152 | 2 | 0.0% / 2.1% / 2.9% | 3.8% | -3.7% / -1.7% / +0.3% | 35.7% / 45.6% / 45.6% | 41.0% | +2.0% / +4.6% / +7.7% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 213 | 2 | 1.6% / 1.9% / 3.7% | 2.5% | -1.8% / -0.6% / -0.4% | 38.2% / 40.0% / 40.7% | 37.2% | +2.2% / +2.8% / +2.8% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 22 | 2 | 0.0% / 0.0% / 0.0% | 1.3% | -1.5% / -1.3% / -0.2% | 35.3% / 48.9% / 48.9% | 33.4% | +10.7% / +15.5% / +15.5% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 6213 | 24 | 6.9% / 8.9% / 11.7% | 10.8% | -2.7% / -1.9% / -1.1% | 24.1% / 28.2% / 33.9% | 27.4% | -0.4% / +0.8% / +2.3% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 4.0% / 6.7% / 7.3% | 5.6% | -0.6% / +1.0% / +1.7% | 17.8% / 27.4% / 45.9% | 27.8% | -1.1% / -0.4% / +4.8% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 19499 | 24 | 5.8% / 6.8% / 7.9% | 6.9% | -0.5% / -0.1% / +0.3% | 65.1% / 68.6% / 71.7% | 66.4% | +1.4% / +2.2% / +3.0% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 12.2% / 13.3% / 14.5% | 12.5% | +0.4% / +0.8% / +1.4% | 47.2% / 52.4% / 53.9% | 52.0% | -0.5% / +0.4% / +1.5% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 29334 | 27 | 6.5% / 7.4% / 8.4% | 7.6% | -0.6% / -0.2% / +0.1% | 54.9% / 58.5% / 61.8% | 56.8% | +1.1% / +1.7% / +2.2% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 8.3% / 16.7% / 27.2% | 17.1% | -1.3% / -0.4% / +0.5% | 50.3% / 54.0% / 56.3% | 47.0% | +5.3% / +7.0% / +8.4% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 19049 | 13 | 5.3% / 6.7% / 7.7% | 7.2% | -0.8% / -0.5% / -0.1% | 43.7% / 46.2% / 47.5% | 46.6% | -1.7% / -0.4% / +0.9% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.7% / 10.2% / 13.5% | 9.7% | -0.4% / +0.4% / +1.3% | 52.5% / 58.9% / 64.3% | 56.7% | +0.9% / +2.2% / +3.6% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 25712 | 25 | 6.2% / 7.1% / 8.3% | 7.5% | -0.8% / -0.4% / -0.1% | 57.8% / 60.7% / 63.2% | 58.6% | +1.6% / +2.1% / +2.7% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 9.5% / 10.9% / 12.2% | 10.3% | +0.3% / +0.6% / +1.0% | 39.7% / 44.4% / 47.3% | 44.5% | -0.1% / -0.1% / +1.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 14192 | 15 | 7.4% / 9.6% / 12.8% | 10.9% | -1.9% / -1.4% / -0.4% | 51.4% / 54.0% / 70.9% | 49.7% | +2.4% / +4.4% / +20.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 12490 | 10 | 5.5% / 6.9% / 8.5% | 7.0% | -0.6% / -0.2% / +0.4% | 57.4% / 63.2% / 67.9% | 61.4% | +0.9% / +1.8% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 13226 | 12 | 6.3% / 7.8% / 9.1% | 8.2% | -1.2% / -0.4% / +0.2% | 46.9% / 54.4% / 61.4% | 53.1% | +0.1% / +1.3% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 14643 | 15 | 6.3% / 7.6% / 9.5% | 7.8% | -0.8% / -0.2% / +0.3% | 55.8% / 59.3% / 62.1% | 57.6% | +1.0% / +1.7% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 5.2% / 5.2% / 5.2% | 5.2% | -0.1% / -0.1% / -0.1% | 37.7% / 37.7% / 37.7% | 37.7% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 28285 | 27 | 6.7% / 7.7% / 8.9% | 8.0% | -0.7% / -0.3% / +0.0% | 55.0% / 58.4% / 61.6% | 56.5% | +1.4% / +1.9% / +2.5% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 130 | 2 | 0.0% / 5.1% / 6.0% | 4.7% | -2.4% / +0.5% / +1.3% | 4.8% / 6.2% / 6.4% | 6.2% | -2.0% / +0.0% / +3.9% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 576 | 2 | 1.4% / 2.2% / 2.8% | 2.9% | -0.7% / -0.7% / -0.4% | 31.7% / 50.7% / 51.0% | 47.8% | +1.8% / +2.9% / +2.9% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 2.4% / 2.4% / 2.4% | 2.5% | -0.1% / -0.1% / -0.1% | 40.8% / 40.8% / 40.8% | 39.3% | +1.5% / +1.5% / +1.5% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=MID | 331 | 1 | 2.4% / 2.4% / 2.4% | 3.1% | -0.7% / -0.7% / -0.7% | 28.1% / 28.1% / 28.1% | 26.0% | +2.1% / +2.1% / +2.1% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BEARISH | 331 | 1 | 2.4% / 2.4% / 2.4% | 3.1% | -0.7% / -0.7% / -0.7% | 28.1% / 28.1% / 28.1% | 26.0% | +2.1% / +2.1% / +2.1% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 2.4% / 2.4% / 2.4% | 2.5% | -0.1% / -0.1% / -0.1% | 40.8% / 40.8% / 40.8% | 39.3% | +1.5% / +1.5% / +1.5% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 706 | 2 | 2.4% / 2.9% / 2.9% | 3.3% | -0.7% / -0.4% / -0.1% | 28.1% / 41.7% / 41.7% | 39.5% | +1.5% / +2.3% / +2.3% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 7465, MARK_UNAVAILABLE 5370
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 840, RESOLUTION 6377, TIMEOUT 248

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 7465 | 26 | 12% | -54.8% | -47.8% / -44.9% / -41.7% | -2.1% | OK |
| direction=BEAR | 1386 | 26 | 26% | -38.8% | -26.8% / -20.7% / -15.0% | -2.4% | OK |
| direction=BULL | 6079 | 26 | 8% | -57.1% | -54.0% / -50.4% / -46.7% | -2.1% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 7243 | 26 | 11% | -54.5% | -48.0% / -45.0% / -41.7% | -2.2% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 840 | 10 | 27% | -62.7% | -43.1% / -29.3% / -20.3% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 6377 | 26 | 9% | -54.7% | -51.9% / -48.2% / -44.3% | -2.4% | OK |
| exit_reason=TIMEOUT | 248 | 8 | 36% | -44.4% | -20.0% / -10.7% / -2.1% | +6.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1303 | 19 | 12% | -64.5% | -57.0% / -48.5% / -31.0% | -2.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 24 | 4 | 25% | -58.9% | -82.9% / -39.3% / -11.3% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 4 | 2 | 25% | -31.7% | -32.7% / +19.2% / +36.5% | -0.9% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 74 | 9 | 16% | -38.4% | -43.3% / -27.2% / -12.6% | -3.3% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 5353 | 16 | 10% | -52.7% | -48.8% / -46.3% / -43.9% | -2.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 286 | 11 | 21% | -67.4% | -45.1% / -40.2% / -33.2% | -0.5% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 7084 | 26 | 11% | -54.4% | -48.1% / -45.0% / -41.7% | -2.2% | OK |
| target_state=NONE | 95 | 4 | 21% | -82.5% | -86.2% / -46.3% / -44.5% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 261 | 1 | 5% | -67.8% | -61.7% / -61.7% / -61.7% | -3.1% | INSUFFICIENT_SESSIONS |
| tier=1 | 89 | 1 | 9% | -73.3% | -58.8% / -58.8% / -58.8% | -5.1% | INSUFFICIENT_SESSIONS |
| tier=2 | 109 | 1 | 5% | -84.2% | -71.0% / -71.0% / -71.0% | -4.2% | INSUFFICIENT_SESSIONS |
| tier=A | 1496 | 15 | 12% | -41.7% | -39.7% / -36.3% / -32.1% | -2.2% | INSUFFICIENT_SESSIONS |
| tier=B | 1377 | 16 | 15% | -47.3% | -43.6% / -38.7% / -34.0% | -1.8% | INSUFFICIENT_SESSIONS |
| tier=C | 2852 | 16 | 7% | -58.9% | -55.9% / -52.0% / -48.4% | -2.6% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 434 | 16 | 11% | -65.7% | -63.0% / -54.2% / -48.9% | -2.4% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 280 | 15 | 7% | -34.4% | -43.3% / -39.1% / -35.5% | -0.5% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 189 | 6 | 25% | -64.7% | -66.9% / -35.3% / -17.1% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 673 | 10 | 29% | -61.7% | -44.6% / -26.8% / -13.4% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 5112 | 26 | 0% | -61.9% | -67.3% / -62.1% / -57.3% | -4.2% | OK |
| underlying_state=TARGET_FIRST | 985 | 26 | 53% | +4.3% | +12.9% / +21.3% / +31.2% | +6.3% | OK |
| underlying_state=TIMEOUT | 226 | 8 | 35% | -44.7% | -23.0% / -11.3% / -2.0% | +6.4% | INSUFFICIENT_SESSIONS |

## Forward hypothesis tests

`H9R_GAP_UP_REVERSAL` — pre-registered forward test from 2026-09-17 (SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: UP events, 10-session net return expected negative; verdict needs >= 30 event dates and >= 200 events, clustered t <= -2.0 and |mean| above the median share spread. Measurement only.

| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |
|---|---|---|---|---|---|---|---|
| UP | 5 | 10 | 4 | -292.2 | n/a | 56.9 | SECONDARY |
| UP | 10 | 4 | 1 | 390.7 | n/a | 56.9 | INSUFFICIENT_EVIDENCE |
| UP | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 5 | 8 | 6 | -117.3 | n/a | 0.0 | SECONDARY |
| DOWN | 10 | 1 | 1 | 196.8 | n/a | 0.0 | SECONDARY |
| DOWN | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |

## Signal track record

Candidates considered 1499; tickets issued 5; closed 5 (Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at real prices (options: issue-time ask to exit-session bid). Decision support only.

| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | Predicted central | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 5 | 1 | 0% | -37.3% | n/a | n/a | -37.3% | -65.1% | 92.2% | +5.7% | INSUFFICIENT_EVIDENCE |
| OPTION | 5 | 1 | 0% | -37.3% | n/a | n/a | -37.3% | -65.1% | 92.2% | +5.7% | INSUFFICIENT_EVIDENCE |
| QUOTE_CURRENT_SESSION | 5 | 1 | 0% | -37.3% | n/a | n/a | -37.3% | -65.1% | 92.2% | +5.7% | INSUFFICIENT_EVIDENCE |
| QUOTE_PRIOR_SESSION | 0 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0.0% | n/a | INSUFFICIENT_EVIDENCE |

## Resolution timing (session of first touch)

| State | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AMBIGUOUS | 421 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 3118 | 2214 | 1570 | 1286 | 966 | 678 | 658 | 529 | 418 | 310 | 319 | 259 | 252 | 198 | 179 | 157 | 165 | 134 | 106 | 78 |
| TARGET_FIRST | 584 | 294 | 211 | 186 | 95 | 83 | 62 | 48 | 83 | 51 | 57 | 35 | 34 | 24 | 10 | 16 | 17 | 14 | 4 | 5 |

Caveats: 121 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
