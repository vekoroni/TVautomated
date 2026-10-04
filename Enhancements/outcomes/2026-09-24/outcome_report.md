# Outcome report — as of 2026-09-24

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 30639, RETROSPECTIVE_UNVERIFIED 414
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 1485, THESIS_ID 19603
- **invalidation_state**: MISSING 4277, VALID 26776
- **target_state**: INVALID_LEGACY 8100, LEVEL 18198, NONE 4755
- **contract_state**: MISSING 6382, SIDE_MISMATCH 1361, VALID 23310
- **direction**: BEAR 7664, BULL 21559, None 1830
- **base_state**: NOT_SCORABLE 3908, NO_ATR 11, None 1549, OK 25585
- **macro_freshness**: CURRENT 30360, STALE 693
- **outcome_state**: AMBIGUOUS 307, DATA_GAP 27, NOT_SCORABLE 3908, NOT_YET_SCORED 1549, OPEN_CENSORED 10222, STOP_FIRST 10649, TARGET_FIRST 1544, TIMEOUT 2847

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 25210 | 25 | 6.9% / 7.9% / 9.2% | 8.0% | -0.5% / -0.1% / +0.3% | 56.9% / 60.6% / 63.6% | 58.0% | +1.9% / +2.6% / +3.3% | OK |
| headline | direction=BEAR | 6340 | 24 | 6.0% / 8.1% / 10.7% | 9.4% | -2.3% / -1.4% / -0.3% | 31.2% / 35.3% / 41.1% | 32.8% | +1.1% / +2.6% / +4.0% | OK |
| headline | direction=BULL | 18870 | 24 | 6.9% / 8.1% / 9.5% | 8.0% | -0.3% / +0.1% / +0.5% | 61.8% / 66.3% / 70.5% | 63.9% | +1.7% / +2.4% / +3.3% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 14.3% | -16.2% / -14.3% / -10.9% | 27.3% / 37.5% / 60.0% | 27.7% | +4.0% / +9.8% / +22.8% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 6.5% / 10.5% / 15.6% | 13.3% | -7.8% / -2.8% / +0.7% | 42.1% / 47.6% / 93.4% | 53.7% | -7.1% / -6.2% / +35.6% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 889 | 15 | 0.0% / 0.0% / 0.0% | 0.1% | -0.2% / -0.1% / -0.0% | 53.4% / 65.9% / 82.3% | 58.0% | -2.4% / +8.0% / +23.2% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 13143 | 14 | 6.3% / 12.4% / 15.4% | 14.2% | -3.1% / -1.8% / -0.7% | 45.3% / 54.5% / 60.2% | 48.7% | +3.2% / +5.9% / +9.2% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1896 | 12 | 5.3% / 15.8% / 25.9% | 16.6% | -2.5% / -0.8% / +3.5% | 45.1% / 51.5% / 72.6% | 48.7% | -1.3% / +2.7% / +17.7% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 6 | 3 | 0.0% / 27.8% / 42.9% | 26.6% | -13.0% / +1.1% / +12.0% | 0.0% / 72.2% / 80.0% | 71.5% | -57.4% / +0.7% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 199 | 8 | 0.0% / 2.9% / 9.6% | 10.4% | -9.0% / -7.5% / -1.9% | 21.2% / 67.2% / 76.7% | 56.6% | -7.7% / +10.7% / +12.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 947 | 12 | 0.0% / 0.0% / 0.0% | 1.6% | -3.9% / -1.6% / -0.0% | 44.5% / 58.2% / 65.7% | 54.4% | +1.7% / +3.8% / +10.5% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 12635 | 14 | 6.9% / 8.4% / 10.9% | 11.9% | -5.3% / -3.5% / -1.1% | 45.4% / 67.6% / 79.3% | 52.6% | +3.0% / +15.0% / +24.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2908 | 20 | 5.8% / 9.2% / 21.3% | 9.4% | -3.2% / -0.2% / +1.8% | 51.5% / 63.7% / 69.2% | 61.6% | -1.1% / +2.2% / +4.1% | OK |
| headline | lab_verdict=CONTRACT_REPAIR | 957 | 13 | 0.0% / 0.0% / 0.0% | 1.2% | -3.4% / -1.2% / -0.0% | 50.3% / 66.2% / 80.2% | 61.0% | +2.3% / +5.2% / +19.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 6 | 3 | 0.0% / 27.8% / 42.9% | 26.6% | -13.0% / +1.1% / +12.0% | 0.0% / 72.2% / 80.0% | 71.5% | -57.4% / +0.7% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 224 | 9 | 0.0% / 7.3% / 12.7% | 16.4% | -11.6% / -9.0% / -2.4% | 31.2% / 61.9% / 69.9% | 47.4% | +0.2% / +14.5% / +20.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 12635 | 14 | 6.9% / 8.4% / 10.9% | 11.9% | -5.3% / -3.5% / -1.1% | 45.4% / 67.6% / 79.3% | 52.6% | +3.0% / +15.0% / +24.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.0% / 64.7% / 68.4% | 62.8% | +1.3% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 16563 | 23 | 15.4% / 17.8% / 21.6% | 18.1% | -1.1% / -0.3% / +0.7% | 54.5% / 57.0% / 59.4% | 54.2% | +1.4% / +2.8% / +4.1% | OK |
| headline | target_state=NONE | 1089 | 11 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 40.4% / 56.3% / 61.0% | 44.5% | +3.1% / +11.8% / +17.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 3754 | 9 | 4.2% / 10.7% / 12.1% | 13.7% | -6.7% / -3.0% / -0.5% | 39.8% / 75.2% / 82.4% | 55.5% | +4.1% / +19.7% / +23.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 136 | 9 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 1.2% / 71.1% / 78.3% | 37.9% | -0.3% / +33.2% / +34.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 109 | 8 | 0.0% / 0.0% / 0.0% | 21.1% | -27.7% / -21.1% / -16.4% | 100.0% / 100.0% / 100.0% | 78.4% | +17.1% / +21.6% / +28.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.2% | -0.2% / -0.2% / -0.2% | 34.4% / 34.4% / 34.4% | 37.1% | -2.8% / -2.8% / -2.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 73 | 8 | 65.0% / 82.2% / 87.7% | 31.1% | +40.7% / +51.1% / +55.8% | 12.3% / 17.8% / 35.0% | 68.7% | -55.3% / -50.9% / -40.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 23 | 9 | 0.0% / 0.0% / 0.0% | 1.5% | -6.5% / -1.5% / +0.0% | 8.0% / 36.1% / 70.4% | 35.1% | -21.2% / +1.0% / +21.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 63 | 6 | 0.0% / 17.5% / 48.2% | 5.0% | -1.2% / +12.5% / +39.4% | 18.0% / 26.6% / 31.7% | 35.6% | -14.9% / -9.0% / +3.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 7923 | 12 | 6.7% / 12.1% / 14.8% | 12.2% | -1.7% / -0.1% / +0.7% | 48.5% / 56.1% / 58.9% | 52.7% | +1.2% / +3.5% / +6.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 3400 | 12 | 6.0% / 14.2% / 20.8% | 17.1% | -4.1% / -2.9% / -0.1% | 37.8% / 43.2% / 49.7% | 39.8% | +1.6% / +3.4% / +8.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 170 | 5 | 2.2% / 21.7% / 35.5% | 23.1% | -32.3% / -1.4% / +14.4% | 16.5% / 22.9% / 25.0% | 62.6% | -45.0% / -39.7% / -3.2% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 3.0% / 3.0% / 3.0% | 5.8% | -2.8% / -2.8% / -2.8% | 47.0% / 47.0% / 47.0% | 41.4% | +5.6% / +5.6% / +5.6% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 3.2% / 3.2% / 3.2% | 7.1% | -3.9% / -3.9% / -3.9% | 35.6% / 35.6% / 35.6% | 32.2% | +3.3% / +3.3% / +3.3% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.5% / 1.5% / 1.5% | 2.4% | -0.9% / -0.9% / -0.9% | 32.4% / 32.4% / 32.4% | 26.6% | +5.8% / +5.8% / +5.8% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 3242 | 12 | 7.8% / 20.6% / 23.4% | 14.8% | -1.2% / +5.8% / +7.6% | 39.6% / 46.2% / 56.8% | 52.5% | -11.7% / -6.3% / +4.7% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 2492 | 13 | 9.5% / 16.1% / 19.9% | 17.9% | -3.5% / -1.8% / +2.0% | 42.3% / 56.2% / 60.4% | 51.8% | -4.9% / +4.4% / +6.7% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 6870 | 13 | 5.9% / 11.9% / 14.7% | 13.1% | -2.9% / -1.2% / -0.4% | 47.4% / 60.5% / 68.1% | 49.0% | +4.7% / +11.5% / +16.1% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 1974 | 15 | 2.1% / 3.8% / 7.9% | 6.8% | -4.4% / -3.0% / -0.4% | 38.9% / 50.1% / 65.7% | 46.2% | -2.7% / +3.9% / +18.2% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 83 | 1 | 2.4% / 2.4% / 2.4% | 2.7% | -0.3% / -0.3% / -0.3% | 2.4% / 2.4% / 2.4% | 4.1% | -1.7% / -1.7% / -1.7% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 292 | 1 | 1.0% / 1.0% / 1.0% | 1.0% | -0.0% / -0.0% / -0.0% | 31.8% / 31.8% / 31.8% | 31.3% | +0.5% / +0.5% / +0.5% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 38 | 1 | 13.2% / 13.2% / 13.2% | 6.6% | +6.6% / +6.6% / +6.6% | 86.8% / 86.8% / 86.8% | 84.0% | +2.9% / +2.9% / +2.9% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 0.9% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.6% | -0.6% / -0.6% / -0.6% | 30.0% / 30.0% / 30.0% | 25.4% | +4.6% / +4.6% / +4.6% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 23.6% | +9.8% / +9.8% / +9.8% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 302 | 1 | 0.0% / 0.0% / 0.0% | 0.8% | -0.8% / -0.8% / -0.8% | 17.2% / 17.2% / 17.2% | 18.1% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 38 | 1 | 13.2% / 13.2% / 13.2% | 6.6% | +6.6% / +6.6% / +6.6% | 86.8% / 86.8% / 86.8% | 84.0% | +2.9% / +2.9% / +2.9% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 23.6% | +9.8% / +9.8% / +9.8% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 0.9% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.6% | -0.6% / -0.6% / -0.6% | 30.0% / 30.0% / 30.0% | 25.4% | +4.6% / +4.6% / +4.6% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 302 | 1 | 0.0% / 0.0% / 0.0% | 0.8% | -0.8% / -0.8% / -0.8% | 17.2% / 17.2% / 17.2% | 18.1% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 372 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | -0.1% / -0.1% / -0.1% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 23.6% | +9.8% / +9.8% / +9.8% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 334 | 1 | 0.0% / 0.0% / 0.0% | 0.8% | -0.8% / -0.8% / -0.8% | 18.3% / 18.3% / 18.3% | 18.7% | -0.4% / -0.4% / -0.4% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 23.6% | +9.8% / +9.8% / +9.8% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 28 | 1 | 0.0% / 0.0% / 0.0% | 4.8% | -4.8% / -4.8% / -4.8% | 100.0% / 100.0% / 100.0% | 82.6% | +17.4% / +17.4% / +17.4% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 10 | 1 | 50.0% / 50.0% / 50.0% | 11.7% | +38.3% / +38.3% / +38.3% | 50.0% / 50.0% / 50.0% | 87.8% | -37.8% / -37.8% / -37.8% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 116 | 1 | 1.7% / 1.7% / 1.7% | 2.0% | -0.3% / -0.3% / -0.3% | 29.3% / 29.3% / 29.3% | 29.2% | +0.1% / +0.1% / +0.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 68 | 1 | 1.5% / 1.5% / 1.5% | 1.5% | -0.0% / -0.0% / -0.0% | 29.4% / 29.4% / 29.4% | 26.6% | +2.8% / +2.8% / +2.8% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 186 | 1 | 1.1% / 1.1% / 1.1% | 1.0% | +0.1% / +0.1% / +0.1% | 21.5% / 21.5% / 21.5% | 22.6% | -1.1% / -1.1% / -1.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 5 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 20.0% / 20.0% / 20.0% | 16.8% | +3.2% / +3.2% / +3.2% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 4991 | 21 | 6.1% / 8.5% / 11.8% | 10.2% | -2.6% / -1.7% / -0.7% | 31.7% / 36.1% / 42.1% | 33.6% | +0.8% / +2.5% / +4.3% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 2.5% / 4.8% / 4.9% | 4.2% | -1.2% / +0.6% / +0.8% | 18.0% / 41.2% / 52.9% | 36.7% | +1.0% / +4.6% / +4.6% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 15924 | 21 | 6.1% / 7.2% / 8.6% | 7.2% | -0.4% / +0.1% / +0.6% | 63.9% / 68.4% / 72.2% | 66.0% | +1.5% / +2.4% / +3.4% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 10.7% / 12.6% / 14.3% | 12.4% | -0.2% / +0.2% / +1.2% | 46.7% / 51.6% / 52.9% | 50.0% | +0.3% / +1.6% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 24537 | 24 | 6.6% / 7.6% / 8.7% | 7.7% | -0.5% / -0.1% / +0.3% | 57.1% / 60.9% / 64.0% | 58.4% | +1.7% / +2.4% / +3.2% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 6.9% / 17.7% / 26.8% | 18.3% | -1.8% / -0.6% / +0.7% | 44.2% / 51.3% / 55.5% | 45.9% | +5.1% / +5.5% / +6.3% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 14252 | 10 | 3.9% / 5.6% / 6.7% | 6.2% | -1.2% / -0.6% / -0.1% | 38.8% / 41.4% / 42.5% | 38.9% | -0.8% / +2.5% / +3.3% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.6% / 10.1% / 13.3% | 9.5% | -0.3% / +0.6% / +1.5% | 52.2% / 59.1% / 64.8% | 57.1% | +0.5% / +2.0% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 20915 | 22 | 6.2% / 7.3% / 8.8% | 7.6% | -0.7% / -0.2% / +0.2% | 59.5% / 62.7% / 65.3% | 60.1% | +1.8% / +2.6% / +3.4% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 7.9% / 10.1% / 12.1% | 9.8% | +0.1% / +0.3% / +0.9% | 36.6% / 46.9% / 47.8% | 45.2% | +0.8% / +1.7% / +3.1% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 14192 | 15 | 6.4% / 12.0% / 14.5% | 13.5% | -2.9% / -1.5% / -0.5% | 46.3% / 53.7% / 62.6% | 49.1% | +1.2% / +4.6% / +12.0% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 7693 | 7 | 6.1% / 7.8% / 9.8% | 7.7% | -0.7% / +0.0% / +0.9% | 56.9% / 63.1% / 67.9% | 61.0% | +0.9% / +2.0% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 8429 | 9 | 6.3% / 8.1% / 9.6% | 8.4% | -1.0% / -0.3% / +0.3% | 43.9% / 57.1% / 64.6% | 53.7% | +1.9% / +3.4% / +5.1% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 14643 | 15 | 6.4% / 7.9% / 10.3% | 7.9% | -0.4% / +0.0% / +0.6% | 56.9% / 61.0% / 63.9% | 59.1% | +1.0% / +1.9% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 4.1% / 4.1% / 4.1% | 3.5% | +0.6% / +0.6% / +0.6% | 25.5% / 25.5% / 25.5% | 24.9% | +0.6% / +0.6% / +0.6% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 23488 | 24 | 6.8% / 7.9% / 9.3% | 8.1% | -0.6% / -0.2% / +0.2% | 56.8% / 60.5% / 63.7% | 57.9% | +1.9% / +2.6% / +3.3% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 83 | 1 | 2.4% / 2.4% / 2.4% | 2.7% | -0.3% / -0.3% / -0.3% | 2.4% / 2.4% / 2.4% | 4.1% | -1.7% / -1.7% / -1.7% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 292 | 1 | 1.0% / 1.0% / 1.0% | 1.0% | -0.0% / -0.0% / -0.0% | 31.8% / 31.8% / 31.8% | 31.3% | +0.5% / +0.5% / +0.5% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.4% | -0.1% / -0.1% / -0.1% | 25.3% / 25.3% / 25.3% | 25.3% | +0.0% / +0.0% / +0.0% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 6405, MARK_UNAVAILABLE 2632
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 840, RESOLUTION 5353, TIMEOUT 212

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 6405 | 23 | 12% | -56.0% | -48.4% / -44.8% / -41.3% | -1.9% | OK |
| direction=BEAR | 1295 | 23 | 25% | -40.0% | -29.4% / -22.0% / -15.2% | -2.7% | OK |
| direction=BULL | 5110 | 23 | 9% | -58.6% | -54.3% / -50.6% / -46.8% | -1.8% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 6183 | 23 | 12% | -55.4% | -48.7% / -44.9% / -41.2% | -2.0% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 840 | 10 | 27% | -62.7% | -43.1% / -29.3% / -20.3% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 5353 | 23 | 9% | -55.6% | -52.8% / -48.6% / -44.0% | -2.3% | OK |
| exit_reason=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1235 | 18 | 12% | -64.5% | -57.6% / -49.4% / -33.1% | -2.5% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 24 | 4 | 25% | -58.9% | -82.9% / -39.3% / -11.3% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 56 | 8 | 20% | -44.9% | -48.7% / -26.6% / -9.4% | -3.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 4380 | 13 | 10% | -53.3% | -49.7% / -46.3% / -43.6% | -2.2% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 282 | 11 | 21% | -67.4% | -44.7% / -39.9% / -32.1% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 6028 | 23 | 12% | -55.3% | -48.8% / -45.0% / -41.3% | -2.0% | OK |
| target_state=NONE | 95 | 4 | 21% | -82.5% | -86.2% / -46.3% / -44.5% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 252 | 1 | 4% | -66.7% | -61.1% / -61.1% / -61.1% | -3.0% | INSUFFICIENT_SESSIONS |
| tier=1 | 87 | 1 | 8% | -73.3% | -60.9% / -60.9% / -60.9% | -5.2% | INSUFFICIENT_SESSIONS |
| tier=2 | 98 | 1 | 2% | -83.3% | -76.1% / -76.1% / -76.1% | -4.3% | INSUFFICIENT_SESSIONS |
| tier=A | 1162 | 12 | 12% | -42.7% | -40.3% / -37.3% / -33.5% | -2.2% | INSUFFICIENT_SESSIONS |
| tier=B | 1147 | 13 | 16% | -45.9% | -43.2% / -37.9% / -32.9% | -1.6% | INSUFFICIENT_SESSIONS |
| tier=C | 2415 | 13 | 8% | -59.1% | -56.2% / -51.7% / -47.9% | -2.4% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 397 | 13 | 12% | -65.5% | -62.3% / -53.2% / -47.8% | -2.2% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 280 | 15 | 7% | -34.4% | -43.3% / -39.1% / -35.5% | -0.5% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 167 | 6 | 22% | -66.3% | -65.9% / -39.3% / -22.6% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 673 | 10 | 29% | -61.7% | -44.6% / -26.8% / -13.4% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 4188 | 23 | 0% | -64.1% | -68.9% / -63.1% / -57.7% | -4.1% | OK |
| underlying_state=TARGET_FIRST | 885 | 23 | 51% | +1.9% | +8.3% / +17.0% / +28.7% | +5.9% | OK |
| underlying_state=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |

## Forward hypothesis tests

`H9R_GAP_UP_REVERSAL` — pre-registered forward test from 2026-09-17 (SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: UP events, 10-session net return expected negative; verdict needs >= 30 event dates and >= 200 events, clustered t <= -2.0 and |mean| above the median share spread. Measurement only.

| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |
|---|---|---|---|---|---|---|---|
| UP | 5 | 4 | 1 | -6.3 | n/a | 56.9 | SECONDARY |
| UP | 10 | 0 | 0 | n/a | n/a | n/a | INSUFFICIENT_EVIDENCE |
| UP | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 5 | 1 | 1 | -86.0 | n/a | 0.0 | SECONDARY |
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
| AMBIGUOUS | 304 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 2524 | 1665 | 1303 | 985 | 730 | 494 | 470 | 388 | 310 | 214 | 253 | 227 | 204 | 161 | 142 | 147 | 153 | 119 | 88 | 72 |
| TARGET_FIRST | 519 | 246 | 188 | 149 | 80 | 51 | 44 | 42 | 58 | 30 | 30 | 25 | 21 | 12 | 4 | 12 | 15 | 11 | 3 | 4 |

Caveats: 119 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
