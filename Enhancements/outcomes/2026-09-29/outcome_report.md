# Outcome report — as of 2026-09-29

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 35096, RETROSPECTIVE_UNVERIFIED 414
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 1955, THESIS_ID 23590
- **invalidation_state**: MISSING 5116, VALID 30394
- **target_state**: INVALID_LEGACY 8348, LEVEL 21726, NONE 5436
- **contract_state**: MISSING 6871, SIDE_MISMATCH 1361, VALID 27278
- **direction**: BEAR 8672, BULL 24542, None 2296
- **base_state**: NOT_SCORABLE 4827, NO_ATR 11, None 1570, OK 29102
- **macro_freshness**: CURRENT 34817, STALE 693
- **outcome_state**: AMBIGUOUS 395, DATA_GAP 27, NOT_SCORABLE 4827, NOT_YET_SCORED 1570, OPEN_CENSORED 11804, STOP_FIRST 12249, TARGET_FIRST 1767, TIMEOUT 2871

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 28727 | 27 | 6.7% / 7.8% / 9.1% | 7.9% | -0.5% / -0.1% / +0.2% | 54.9% / 58.5% / 61.7% | 56.5% | +1.4% / +2.0% / +2.6% | OK |
| headline | direction=BEAR | 7264 | 26 | 6.5% / 8.3% / 11.0% | 9.5% | -2.1% / -1.2% / -0.2% | 25.9% / 29.9% / 35.7% | 28.8% | -0.2% / +1.0% / +2.5% | OK |
| headline | direction=BULL | 21463 | 26 | 6.6% / 7.9% / 9.2% | 7.7% | -0.3% / +0.1% / +0.5% | 61.6% / 65.6% / 69.3% | 63.6% | +1.3% / +2.0% / +2.8% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 15.8% | -17.8% / -15.8% / -12.2% | 33.3% / 50.0% / 80.0% | 31.5% | +2.6% / +18.5% / +40.6% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 7.9% / 11.1% / 16.6% | 14.1% | -4.7% / -3.0% / +0.9% | 41.5% / 46.9% / 53.6% | 52.8% | -11.7% / -5.9% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 911 | 17 | 0.0% / 0.0% / 0.0% | 0.2% | -0.3% / -0.2% / -0.1% | 51.0% / 60.9% / 67.5% | 57.5% | -4.3% / +3.3% / +13.0% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 16638 | 16 | 6.8% / 13.0% / 16.8% | 13.2% | -1.2% / -0.2% / +0.9% | 44.4% / 51.4% / 55.6% | 49.2% | +0.5% / +2.2% / +4.0% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1938 | 14 | 5.8% / 15.9% / 25.3% | 16.1% | -3.2% / -0.2% / +3.2% | 47.7% / 55.9% / 72.0% | 51.0% | -4.4% / +4.9% / +13.0% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 10 | 4 | 0.0% / 10.0% / 25.0% | 22.9% | -15.8% / -12.9% / -0.5% | 42.9% / 90.0% / 100.0% | 75.4% | -0.2% / +14.6% / +45.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 347 | 10 | 0.3% / 2.4% / 6.0% | 9.7% | -9.6% / -7.2% / -1.4% | 28.8% / 48.4% / 68.4% | 58.6% | -18.8% / -10.2% / +8.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 981 | 14 | 0.0% / 0.0% / 0.0% | 1.3% | -3.6% / -1.3% / -0.1% | 39.8% / 56.5% / 64.2% | 53.1% | -5.0% / +3.3% / +15.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 15924 | 16 | 7.1% / 8.4% / 10.2% | 11.6% | -4.8% / -3.1% / -0.3% | 44.6% / 47.4% / 54.2% | 52.1% | -6.8% / -4.7% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 3037 | 22 | 5.7% / 9.2% / 20.1% | 9.6% | -3.3% / -0.4% / +1.5% | 52.0% / 61.6% / 68.9% | 59.4% | -0.5% / +2.2% / +6.0% | OK |
| headline | lab_verdict=CONTRACT_REPAIR | 991 | 15 | 0.0% / 0.0% / 0.0% | 1.1% | -3.1% / -1.1% / -0.1% | 46.9% / 60.7% / 74.5% | 54.6% | -2.1% / +6.1% / +19.7% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 6 | 3 | 0.0% / 16.7% / 28.6% | 24.3% | -15.9% / -7.6% / +2.5% | 66.7% / 83.3% / 100.0% | 74.1% | -5.5% / +9.2% / +49.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 291 | 10 | 1.3% / 4.8% / 9.4% | 14.2% | -11.4% / -9.3% / -1.7% | 31.6% / 54.2% / 66.0% | 46.5% | -15.2% / +7.7% / +16.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 15922 | 16 | 7.1% / 8.4% / 10.2% | 11.6% | -4.8% / -3.1% / -0.3% | 44.6% / 47.4% / 54.2% | 52.1% | -6.8% / -4.7% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 59.5% / 64.4% / 68.1% | 62.5% | +1.2% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 19979 | 25 | 13.3% / 15.5% / 19.0% | 15.6% | -0.8% / -0.2% / +0.7% | 51.3% / 53.7% / 56.6% | 52.6% | +0.0% / +1.1% / +2.5% | OK |
| headline | target_state=NONE | 1190 | 13 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 27.6% / 47.9% / 58.4% | 43.0% | -1.4% / +4.9% / +15.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 4499 | 11 | 4.8% / 6.1% / 10.1% | 12.4% | -9.2% / -6.4% / -0.5% | 41.9% / 46.8% / 75.0% | 57.3% | -11.0% / -10.5% / +16.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 154 | 11 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.8% / 32.4% / 67.7% | 36.0% | -5.8% / -3.6% / +28.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 142 | 10 | 0.0% / 0.0% / 0.0% | 19.8% | -25.0% / -19.8% / -15.4% | 100.0% / 100.0% / 100.0% | 79.7% | +16.7% / +20.3% / +25.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.3% | -0.3% / -0.3% / -0.3% | 34.4% / 34.4% / 34.4% | 41.0% | -6.6% / -6.6% / -6.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 81 | 10 | 51.5% / 76.5% / 84.9% | 29.6% | +30.2% / +47.0% / +53.3% | 15.1% / 23.5% / 48.5% | 70.3% | -53.1% / -46.9% / -29.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 29 | 11 | 0.0% / 0.0% / 0.0% | 1.4% | -5.4% / -1.4% / +0.0% | 10.8% / 31.0% / 44.9% | 30.4% | -19.3% / +0.6% / +12.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 104 | 8 | 0.0% / 11.7% / 41.3% | 4.7% | -2.1% / +7.1% / +33.3% | 12.2% / 20.2% / 26.6% | 39.8% | -26.5% / -19.6% / -9.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 9516 | 14 | 6.5% / 13.3% / 16.1% | 11.4% | -1.4% / +1.9% / +3.3% | 48.4% / 51.4% / 55.0% | 53.7% | -4.5% / -2.3% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 4369 | 14 | 7.6% / 12.2% / 19.5% | 15.9% | -4.8% / -3.7% / +0.6% | 35.4% / 51.0% / 54.2% | 39.9% | -1.7% / +11.1% / +14.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 274 | 7 | 1.5% / 3.6% / 19.3% | 21.5% | -19.3% / -17.8% / +8.7% | 31.2% / 36.8% / 39.0% | 62.5% | -41.6% / -25.6% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 3.8% / 3.8% / 3.8% | 6.4% | -2.6% / -2.6% / -2.6% | 49.8% / 49.8% / 49.8% | 45.0% | +4.8% / +4.8% / +4.8% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 5.1% / 5.1% / 5.1% | 8.3% | -3.2% / -3.2% / -3.2% | 37.2% / 37.2% / 37.2% | 35.6% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.8% / 1.8% / 1.8% | 3.0% | -1.1% / -1.1% / -1.1% | 37.0% / 37.0% / 37.0% | 30.9% | +6.1% / +6.1% / +6.1% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 4685 | 14 | 8.0% / 11.2% / 21.4% | 13.8% | -3.5% / -2.6% / +5.5% | 39.5% / 41.9% / 48.1% | 52.9% | -12.8% / -11.0% / -3.7% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 3072 | 15 | 9.4% / 16.8% / 19.6% | 16.7% | -2.2% / +0.1% / +2.2% | 41.5% / 48.5% / 55.1% | 52.7% | -8.0% / -4.1% / +0.0% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 8158 | 15 | 6.3% / 15.4% / 22.2% | 12.3% | -2.0% / +3.1% / +7.7% | 47.1% / 63.7% / 65.9% | 49.3% | +2.6% / +14.5% / +16.1% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 2180 | 17 | 2.1% / 3.8% / 7.8% | 6.4% | -4.1% / -2.6% / +0.2% | 38.6% / 48.9% / 56.1% | 45.4% | -3.6% / +3.5% / +11.7% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 83 | 1 | 4.8% / 4.8% / 4.8% | 3.8% | +1.0% / +1.0% / +1.0% | 3.6% / 3.6% / 3.6% | 5.8% | -2.2% / -2.2% / -2.2% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 292 | 1 | 1.4% / 1.4% / 1.4% | 1.5% | -0.2% / -0.2% / -0.2% | 42.5% / 42.5% / 42.5% | 41.5% | +1.0% / +1.0% / +1.0% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 38 | 1 | 13.2% / 13.2% / 13.2% | 7.7% | +5.5% / +5.5% / +5.5% | 86.8% / 86.8% / 86.8% | 88.3% | -1.5% / -1.5% / -1.5% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 2.9% | -2.9% / -2.9% / -2.9% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 30 | 1 | 3.3% / 3.3% / 3.3% | 1.0% | +2.3% / +2.3% / +2.3% | 33.3% / 33.3% / 33.3% | 36.6% | -3.3% / -3.3% / -3.3% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 28.6% | +4.7% / +4.7% / +4.7% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 302 | 1 | 0.7% / 0.7% / 0.7% | 1.5% | -0.8% / -0.8% / -0.8% | 27.5% / 27.5% / 27.5% | 26.7% | +0.8% / +0.8% / +0.8% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 38 | 1 | 13.2% / 13.2% / 13.2% | 7.7% | +5.5% / +5.5% / +5.5% | 86.8% / 86.8% / 86.8% | 88.3% | -1.5% / -1.5% / -1.5% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 28.6% | +4.7% / +4.7% / +4.7% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 2.9% | -2.9% / -2.9% / -2.9% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 30 | 1 | 3.3% / 3.3% / 3.3% | 1.0% | +2.3% / +2.3% / +2.3% | 33.3% / 33.3% / 33.3% | 36.6% | -3.3% / -3.3% / -3.3% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 302 | 1 | 0.7% / 0.7% / 0.7% | 1.5% | -0.8% / -0.8% / -0.8% | 27.5% / 27.5% / 27.5% | 26.7% | +0.8% / +0.8% / +0.8% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 372 | 1 | 2.2% / 2.2% / 2.2% | 2.1% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.2% / +0.2% / +0.2% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 28.6% | +4.7% / +4.7% / +4.7% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 334 | 1 | 0.9% / 0.9% / 0.9% | 1.4% | -0.5% / -0.5% / -0.5% | 27.8% / 27.8% / 27.8% | 27.4% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 28.6% | +4.7% / +4.7% / +4.7% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 28 | 1 | 0.0% / 0.0% / 0.0% | 6.3% | -6.3% / -6.3% / -6.3% | 100.0% / 100.0% / 100.0% | 88.3% | +11.7% / +11.7% / +11.7% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 10 | 1 | 50.0% / 50.0% / 50.0% | 11.8% | +38.2% / +38.2% / +38.2% | 50.0% / 50.0% / 50.0% | 88.1% | -38.1% / -38.1% / -38.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 116 | 1 | 3.4% / 3.4% / 3.4% | 2.8% | +0.6% / +0.6% / +0.6% | 39.7% / 39.7% / 39.7% | 38.6% | +1.1% / +1.1% / +1.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 68 | 1 | 2.9% / 2.9% / 2.9% | 2.2% | +0.8% / +0.8% / +0.8% | 32.4% / 32.4% / 32.4% | 35.0% | -2.6% / -2.6% / -2.6% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 186 | 1 | 1.1% / 1.1% / 1.1% | 1.5% | -0.5% / -0.5% / -0.5% | 31.2% / 31.2% / 31.2% | 30.3% | +0.9% / +0.9% / +0.9% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 5 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 20.0% / 20.0% / 20.0% | 23.9% | -3.9% / -3.9% / -3.9% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 5915 | 23 | 6.6% / 8.9% / 12.1% | 10.3% | -2.3% / -1.4% / -0.3% | 26.5% / 30.8% / 37.0% | 29.5% | -0.1% / +1.3% / +2.9% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 3.1% / 5.6% / 6.2% | 4.8% | -0.8% / +0.8% / +1.4% | 17.6% / 36.1% / 48.5% | 32.8% | +1.2% / +3.3% / +3.6% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 18517 | 23 | 5.9% / 6.9% / 8.1% | 6.9% | -0.4% / +0.0% / +0.4% | 63.8% / 67.8% / 71.4% | 65.7% | +1.3% / +2.1% / +3.1% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 12.0% / 13.3% / 14.5% | 12.5% | +0.4% / +0.8% / +1.4% | 47.2% / 51.8% / 53.8% | 51.2% | -0.5% / +0.5% / +1.7% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 28054 | 26 | 6.5% / 7.5% / 8.5% | 7.5% | -0.4% / -0.1% / +0.3% | 54.8% / 58.7% / 62.0% | 56.9% | +1.2% / +1.8% / +2.4% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 8.4% / 19.4% / 28.1% | 18.7% | -0.3% / +0.7% / +2.3% | 46.4% / 52.8% / 55.4% | 47.3% | +3.8% / +5.6% / +7.2% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 17769 | 12 | 4.9% / 6.3% / 7.4% | 6.5% | -0.7% / -0.1% / +0.3% | 39.6% / 42.0% / 43.3% | 42.1% | -2.2% / -0.0% / +1.5% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.7% / 10.2% / 13.6% | 9.6% | -0.3% / +0.6% / +1.4% | 51.8% / 58.7% / 64.2% | 56.8% | +0.4% / +1.9% / +3.3% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 24432 | 24 | 6.2% / 7.2% / 8.6% | 7.4% | -0.6% / -0.2% / +0.1% | 57.4% / 60.8% / 63.5% | 58.7% | +1.5% / +2.1% / +2.8% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 8.9% / 10.7% / 12.2% | 10.0% | +0.4% / +0.7% / +1.0% | 37.0% / 45.6% / 47.5% | 45.2% | +0.1% / +0.4% / +1.5% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 14192 | 15 | 7.3% / 12.5% / 15.8% | 12.9% | -1.1% / -0.4% / +0.7% | 44.7% / 50.7% / 54.6% | 49.2% | -4.4% / +1.5% / +3.7% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 11210 | 9 | 5.6% / 7.0% / 8.7% | 7.1% | -0.7% / -0.1% / +0.6% | 57.3% / 63.2% / 68.0% | 61.3% | +0.9% / +1.9% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 11946 | 11 | 6.3% / 7.9% / 9.3% | 8.0% | -0.8% / -0.2% / +0.4% | 43.0% / 54.9% / 62.4% | 53.1% | +0.5% / +1.8% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 14643 | 15 | 6.3% / 7.7% / 9.9% | 7.7% | -0.5% / -0.1% / +0.5% | 55.0% / 59.2% / 62.1% | 57.6% | +0.7% / +1.6% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 4.9% / 4.9% / 4.9% | 4.6% | +0.4% / +0.4% / +0.4% | 32.6% / 32.6% / 32.6% | 32.5% | +0.1% / +0.1% / +0.1% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 27005 | 26 | 6.8% / 7.8% / 9.1% | 7.9% | -0.5% / -0.1% / +0.2% | 54.9% / 58.5% / 61.8% | 56.5% | +1.4% / +2.0% / +2.6% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 83 | 1 | 4.8% / 4.8% / 4.8% | 3.8% | +1.0% / +1.0% / +1.0% | 3.6% / 3.6% / 3.6% | 5.8% | -2.2% / -2.2% / -2.2% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 292 | 1 | 1.4% / 1.4% / 1.4% | 1.5% | -0.2% / -0.2% / -0.2% | 42.5% / 42.5% / 42.5% | 41.5% | +1.0% / +1.0% / +1.0% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 375 | 1 | 2.1% / 2.1% / 2.1% | 2.0% | +0.1% / +0.1% / +0.1% | 33.9% / 33.9% / 33.9% | 33.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 6840, MARK_UNAVAILABLE 4037
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 840, RESOLUTION 5760, TIMEOUT 240

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 6840 | 25 | 12% | -55.1% | -47.8% / -44.6% / -41.2% | -2.0% | OK |
| direction=BEAR | 1347 | 25 | 26% | -39.0% | -27.8% / -21.0% / -14.4% | -2.5% | OK |
| direction=BULL | 5493 | 25 | 9% | -57.9% | -53.8% / -50.4% / -46.8% | -1.9% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 6618 | 25 | 12% | -54.8% | -48.0% / -44.7% / -41.2% | -2.0% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 840 | 10 | 27% | -62.7% | -43.1% / -29.3% / -20.3% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 5760 | 25 | 9% | -55.0% | -52.1% / -48.3% / -44.1% | -2.3% | OK |
| exit_reason=TIMEOUT | 240 | 7 | 37% | -43.7% | -18.3% / -9.9% / -0.3% | +6.7% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1282 | 19 | 12% | -63.9% | -57.0% / -48.2% / -30.6% | -2.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 24 | 4 | 25% | -58.9% | -82.9% / -39.3% / -11.3% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 66 | 9 | 18% | -37.1% | -44.1% / -25.9% / -10.0% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 4758 | 15 | 10% | -52.8% | -49.2% / -46.2% / -43.9% | -2.2% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 282 | 11 | 21% | -67.4% | -44.7% / -39.9% / -32.1% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 6463 | 25 | 12% | -54.8% | -48.1% / -44.8% / -41.2% | -2.0% | OK |
| target_state=NONE | 95 | 4 | 21% | -82.5% | -86.2% / -46.3% / -44.5% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 256 | 1 | 5% | -66.9% | -61.0% / -61.0% / -61.0% | -3.0% | INSUFFICIENT_SESSIONS |
| tier=1 | 88 | 1 | 9% | -73.0% | -58.4% / -58.4% / -58.4% | -5.0% | INSUFFICIENT_SESSIONS |
| tier=2 | 103 | 1 | 3% | -83.8% | -74.1% / -74.1% / -74.1% | -4.3% | INSUFFICIENT_SESSIONS |
| tier=A | 1293 | 14 | 12% | -42.5% | -40.2% / -37.3% / -33.5% | -2.3% | INSUFFICIENT_SESSIONS |
| tier=B | 1242 | 15 | 16% | -46.7% | -43.3% / -37.7% / -32.6% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=C | 2599 | 15 | 8% | -58.3% | -55.3% / -51.1% / -47.6% | -2.4% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 412 | 15 | 11% | -66.6% | -64.0% / -54.3% / -48.9% | -2.3% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 280 | 15 | 7% | -34.4% | -43.3% / -39.1% / -35.5% | -0.5% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 188 | 6 | 25% | -63.6% | -65.9% / -34.9% / -16.7% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 673 | 10 | 29% | -61.7% | -44.6% / -26.8% / -13.4% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 4555 | 25 | 0% | -62.9% | -68.0% / -62.6% / -57.7% | -4.1% | OK |
| underlying_state=TARGET_FIRST | 925 | 25 | 53% | +3.6% | +10.9% / +19.6% / +30.4% | +6.1% | OK |
| underlying_state=TIMEOUT | 219 | 7 | 36% | -44.6% | -21.7% / -10.8% / -0.4% | +6.7% | INSUFFICIENT_SESSIONS |

## Forward hypothesis tests

`H9R_GAP_UP_REVERSAL` — pre-registered forward test from 2026-09-17 (SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: UP events, 10-session net return expected negative; verdict needs >= 30 event dates and >= 200 events, clustered t <= -2.0 and |mean| above the median share spread. Measurement only.

| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |
|---|---|---|---|---|---|---|---|
| UP | 5 | 8 | 3 | -441.3 | n/a | 56.9 | SECONDARY |
| UP | 10 | 0 | 0 | n/a | n/a | n/a | INSUFFICIENT_EVIDENCE |
| UP | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 5 | 5 | 4 | -26.1 | n/a | 0.0 | SECONDARY |
| DOWN | 10 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
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
| AMBIGUOUS | 392 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 2940 | 2010 | 1486 | 1106 | 852 | 594 | 563 | 442 | 340 | 238 | 293 | 252 | 224 | 165 | 147 | 155 | 158 | 122 | 88 | 74 |
| TARGET_FIRST | 569 | 269 | 203 | 168 | 88 | 75 | 58 | 43 | 71 | 41 | 50 | 33 | 27 | 13 | 5 | 16 | 17 | 12 | 4 | 5 |

Caveats: 119 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
