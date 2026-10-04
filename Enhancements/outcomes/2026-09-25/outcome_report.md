# Outcome report — as of 2026-09-25

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 33189, RETROSPECTIVE_UNVERIFIED 414
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 1778, THESIS_ID 21860
- **invalidation_state**: MISSING 4801, VALID 28802
- **target_state**: INVALID_LEGACY 8253, LEVEL 20177, NONE 5173
- **contract_state**: MISSING 6687, SIDE_MISMATCH 1361, VALID 25555
- **direction**: BEAR 8260, BULL 23223, None 2120
- **base_state**: NOT_SCORABLE 4351, NO_ATR 11, None 1983, OK 27258
- **macro_freshness**: CURRENT 32910, STALE 693
- **outcome_state**: AMBIGUOUS 375, DATA_GAP 27, NOT_SCORABLE 4351, NOT_YET_SCORED 1983, OPEN_CENSORED 11295, STOP_FIRST 11067, TARGET_FIRST 1658, TIMEOUT 2847

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 26883 | 26 | 7.0% / 8.0% / 9.3% | 8.1% | -0.4% / -0.0% / +0.3% | 56.0% / 59.7% / 62.8% | 57.2% | +1.8% / +2.5% / +3.2% | OK |
| headline | direction=BEAR | 6826 | 25 | 6.2% / 8.1% / 10.9% | 9.3% | -2.1% / -1.2% / -0.2% | 30.2% / 33.9% / 39.5% | 31.7% | +0.9% / +2.2% / +3.7% | OK |
| headline | direction=BULL | 20057 | 25 | 7.1% / 8.3% / 9.6% | 8.1% | -0.2% / +0.2% / +0.6% | 61.2% / 65.7% / 69.7% | 63.3% | +1.6% / +2.4% / +3.2% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 15.4% | -17.2% / -15.4% / -11.6% | 33.3% / 68.8% / 80.0% | 28.1% | +5.9% / +40.7% / +43.4% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 6.8% / 12.8% / 17.6% | 13.6% | -6.8% / -0.8% / +2.3% | 42.8% / 48.2% / 92.8% | 49.9% | -10.4% / -1.8% / +35.7% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 898 | 16 | 0.0% / 0.0% / 0.0% | 0.2% | -0.2% / -0.2% / -0.0% | 50.3% / 61.4% / 73.8% | 55.5% | -2.8% / +5.8% / +16.0% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 14807 | 15 | 7.2% / 15.0% / 16.8% | 13.9% | -1.8% / +1.1% / +1.6% | 43.7% / 49.8% / 57.8% | 47.2% | +1.7% / +2.7% / +8.2% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1924 | 13 | 5.7% / 16.8% / 25.2% | 16.5% | -1.7% / +0.3% / +3.3% | 46.0% / 51.2% / 71.5% | 49.0% | -3.3% / +2.2% / +16.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 6 | 3 | 0.0% / 16.7% / 28.6% | 25.8% | -15.0% / -9.2% / +2.9% | 66.7% / 83.3% / 100.0% | 72.4% | -5.2% / +11.0% / +42.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 266 | 9 | 0.4% / 3.5% / 9.6% | 11.5% | -9.8% / -8.0% / -1.2% | 20.4% / 65.6% / 70.4% | 53.5% | -7.4% / +12.0% / +13.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 965 | 13 | 0.0% / 0.0% / 0.0% | 1.5% | -4.0% / -1.5% / -0.0% | 38.4% / 52.7% / 61.1% | 51.9% | -1.9% / +0.8% / +9.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 14195 | 15 | 7.6% / 9.8% / 11.6% | 12.1% | -5.0% / -2.2% / +0.1% | 44.3% / 49.9% / 78.0% | 49.4% | +0.1% / +0.5% / +23.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2936 | 21 | 5.9% / 9.4% / 21.6% | 9.5% | -2.7% / -0.1% / +1.7% | 51.9% / 63.4% / 69.5% | 61.1% | -0.4% / +2.3% / +4.3% | OK |
| headline | lab_verdict=CONTRACT_REPAIR | 975 | 14 | 0.0% / 0.0% / 0.0% | 1.2% | -3.6% / -1.2% / -0.0% | 46.1% / 61.7% / 78.8% | 57.9% | -0.7% / +3.9% / +21.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 6 | 3 | 0.0% / 16.7% / 28.6% | 25.8% | -15.0% / -9.2% / +2.9% | 66.7% / 83.3% / 100.0% | 72.4% | -5.2% / +11.0% / +42.8% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 291 | 10 | 0.9% / 7.2% / 12.4% | 16.1% | -11.1% / -8.9% / -1.8% | 29.8% / 56.5% / 67.8% | 45.7% | -1.0% / +10.8% / +15.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 14195 | 15 | 7.6% / 9.8% / 11.6% | 12.1% | -5.0% / -2.2% / +0.1% | 44.3% / 49.9% / 78.0% | 49.4% | +0.1% / +0.5% / +23.1% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 59.8% / 64.6% / 68.3% | 62.7% | +1.3% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 18176 | 24 | 15.3% / 17.5% / 21.1% | 17.5% | -0.7% / +0.0% / +0.9% | 53.2% / 55.5% / 58.0% | 53.0% | +1.3% / +2.5% / +3.9% | OK |
| headline | target_state=NONE | 1149 | 12 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 30.9% / 51.4% / 58.2% | 42.1% | +0.3% / +9.3% / +15.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 4208 | 10 | 5.2% / 7.2% / 12.0% | 14.4% | -7.9% / -7.2% / +0.1% | 40.0% / 74.8% / 81.1% | 53.5% | +4.0% / +21.4% / +22.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 148 | 10 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 1.1% / 68.4% / 77.3% | 36.3% | -0.7% / +32.1% / +32.8% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 129 | 9 | 0.0% / 0.0% / 0.0% | 20.9% | -26.4% / -20.9% / -17.0% | 100.0% / 100.0% / 100.0% | 78.6% | +17.8% / +21.4% / +27.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.2% | -0.2% / -0.2% / -0.2% | 34.4% / 34.4% / 34.4% | 38.1% | -3.7% / -3.7% / -3.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 80 | 9 | 53.6% / 77.5% / 85.9% | 30.0% | +30.9% / +47.5% / +53.5% | 14.1% / 22.5% / 46.4% | 69.8% | -53.3% / -47.3% / -30.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 26 | 10 | 0.0% / 0.0% / 0.0% | 1.8% | -6.8% / -1.8% / +0.0% | 6.9% / 25.3% / 55.8% | 32.4% | -24.8% / -7.1% / +16.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 82 | 7 | 0.0% / 17.2% / 46.9% | 5.0% | -1.7% / +12.2% / +38.5% | 14.6% / 21.4% / 25.9% | 34.3% | -19.1% / -13.0% / -2.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 8611 | 13 | 7.4% / 13.3% / 15.3% | 12.2% | -1.6% / +1.1% / +1.6% | 47.5% / 51.4% / 56.5% | 50.9% | -1.0% / +0.4% / +5.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 3828 | 13 | 6.8% / 18.6% / 22.8% | 16.3% | -1.5% / +2.2% / +3.0% | 37.7% / 45.9% / 51.3% | 39.0% | +2.1% / +6.9% / +11.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 212 | 6 | 1.7% / 20.6% / 23.3% | 25.1% | -28.2% / -4.4% / +12.8% | 18.2% / 24.9% / 27.9% | 57.6% | -46.7% / -32.7% / -1.1% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 3.4% / 3.4% / 3.4% | 6.0% | -2.6% / -2.6% / -2.6% | 48.3% / 48.3% / 48.3% | 42.4% | +5.9% / +5.9% / +5.9% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 4.0% / 4.0% / 4.0% | 7.4% | -3.5% / -3.5% / -3.5% | 35.6% / 35.6% / 35.6% | 33.2% | +2.4% / +2.4% / +2.4% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.5% / 1.5% / 1.5% | 2.6% | -1.1% / -1.1% / -1.1% | 33.9% / 33.9% / 33.9% | 27.8% | +6.2% / +6.2% / +6.2% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 3792 | 13 | 8.4% / 21.3% / 23.8% | 14.7% | -0.9% / +6.6% / +8.0% | 38.3% / 43.7% / 51.5% | 50.8% | -10.9% / -7.1% / +1.2% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 2780 | 14 | 10.0% / 16.6% / 20.0% | 17.7% | -3.6% / -1.2% / +2.0% | 41.8% / 50.1% / 59.9% | 50.8% | -5.4% / -0.7% / +6.2% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 7597 | 14 | 6.5% / 18.3% / 19.5% | 12.9% | -2.0% / +5.4% / +5.7% | 46.3% / 51.8% / 64.4% | 47.2% | +3.8% / +4.6% / +14.1% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 2082 | 16 | 2.7% / 6.9% / 11.4% | 6.6% | -3.5% / +0.3% / +4.8% | 36.7% / 45.8% / 58.0% | 43.5% | -3.6% / +2.3% / +11.9% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 83 | 1 | 4.8% / 4.8% / 4.8% | 3.0% | +1.9% / +1.9% / +1.9% | 2.4% / 2.4% / 2.4% | 4.9% | -2.5% / -2.5% / -2.5% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 292 | 1 | 1.0% / 1.0% / 1.0% | 1.2% | -0.2% / -0.2% / -0.2% | 35.3% / 35.3% / 35.3% | 34.0% | +1.2% / +1.2% / +1.2% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 38 | 1 | 13.2% / 13.2% / 13.2% | 7.1% | +6.1% / +6.1% / +6.1% | 86.8% / 86.8% / 86.8% | 85.8% | +1.1% / +1.1% / +1.1% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 1.2% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.7% | -0.7% / -0.7% / -0.7% | 30.0% / 30.0% / 30.0% | 28.4% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 25.3% | +8.0% / +8.0% / +8.0% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 302 | 1 | 0.7% / 0.7% / 0.7% | 1.0% | -0.4% / -0.4% / -0.4% | 20.5% / 20.5% / 20.5% | 20.4% | +0.1% / +0.1% / +0.1% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 38 | 1 | 13.2% / 13.2% / 13.2% | 7.1% | +6.1% / +6.1% / +6.1% | 86.8% / 86.8% / 86.8% | 85.8% | +1.1% / +1.1% / +1.1% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 25.3% | +8.0% / +8.0% / +8.0% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | 0.0% / 0.0% / 0.0% | 1.2% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.7% | -0.7% / -0.7% / -0.7% | 30.0% / 30.0% / 30.0% | 28.4% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 302 | 1 | 0.7% / 0.7% / 0.7% | 1.0% | -0.4% / -0.4% / -0.4% | 20.5% / 20.5% / 20.5% | 20.4% | +0.1% / +0.1% / +0.1% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 372 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 25.3% | +8.0% / +8.0% / +8.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 334 | 1 | 0.6% / 0.6% / 0.6% | 1.0% | -0.4% / -0.4% / -0.4% | 21.3% / 21.3% / 21.3% | 21.0% | +0.3% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 25.3% | +8.0% / +8.0% / +8.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 28 | 1 | 0.0% / 0.0% / 0.0% | 5.4% | -5.4% / -5.4% / -5.4% | 100.0% / 100.0% / 100.0% | 85.0% | +15.0% / +15.0% / +15.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 10 | 1 | 50.0% / 50.0% / 50.0% | 11.8% | +38.2% / +38.2% / +38.2% | 50.0% / 50.0% / 50.0% | 88.0% | -38.0% / -38.0% / -38.0% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 116 | 1 | 2.6% / 2.6% / 2.6% | 2.3% | +0.3% / +0.3% / +0.3% | 30.2% / 30.2% / 30.2% | 31.8% | -1.7% / -1.7% / -1.7% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 68 | 1 | 2.9% / 2.9% / 2.9% | 1.7% | +1.2% / +1.2% / +1.2% | 29.4% / 29.4% / 29.4% | 28.9% | +0.5% / +0.5% / +0.5% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 186 | 1 | 1.1% / 1.1% / 1.1% | 1.2% | -0.1% / -0.1% / -0.1% | 26.3% / 26.3% / 26.3% | 24.7% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 5 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 20.0% / 20.0% / 20.0% | 18.6% | +1.4% / +1.4% / +1.4% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 5477 | 22 | 6.2% / 8.5% / 11.7% | 10.1% | -2.5% / -1.6% / -0.5% | 30.5% / 34.6% / 40.5% | 32.4% | +0.7% / +2.2% / +3.9% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 2.8% / 5.2% / 5.5% | 4.3% | -0.9% / +0.9% / +1.2% | 18.5% / 40.1% / 50.9% | 35.2% | +1.3% / +4.9% / +4.9% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 17111 | 22 | 6.4% / 7.4% / 8.6% | 7.3% | -0.4% / +0.1% / +0.6% | 63.6% / 67.9% / 71.7% | 65.5% | +1.5% / +2.4% / +3.4% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 11.5% / 13.0% / 14.3% | 12.4% | +0.3% / +0.6% / +1.2% | 47.2% / 51.9% / 53.3% | 50.3% | +0.6% / +1.6% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 26210 | 25 | 6.8% / 7.7% / 8.7% | 7.7% | -0.4% / -0.0% / +0.4% | 56.1% / 59.9% / 63.1% | 57.6% | +1.7% / +2.3% / +3.0% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 8.5% / 19.8% / 27.9% | 18.2% | -0.7% / +1.6% / +1.8% | 45.2% / 51.3% / 56.2% | 46.0% | +5.2% / +5.3% / +6.6% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 15925 | 11 | 4.6% / 6.4% / 7.4% | 6.4% | -0.8% / +0.0% / +0.4% | 38.0% / 40.8% / 41.7% | 39.1% | -0.2% / +1.6% / +3.2% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.6% / 10.1% / 13.4% | 9.5% | -0.2% / +0.6% / +1.5% | 52.0% / 58.9% / 64.5% | 56.9% | +0.5% / +2.0% / +3.4% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 22588 | 23 | 6.4% / 7.4% / 8.8% | 7.6% | -0.6% / -0.2% / +0.2% | 58.5% / 61.9% / 64.6% | 59.4% | +1.8% / +2.5% / +3.4% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 8.5% / 10.5% / 12.1% | 9.9% | +0.4% / +0.6% / +0.9% | 37.2% / 46.8% / 47.8% | 45.2% | +1.0% / +1.6% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 14192 | 15 | 7.4% / 14.2% / 16.1% | 13.2% | -1.9% / +1.0% / +1.4% | 45.1% / 50.4% / 60.1% | 47.5% | -0.5% / +2.9% / +8.8% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 9366 | 8 | 6.1% / 7.8% / 9.7% | 7.8% | -0.7% / -0.0% / +0.7% | 57.1% / 62.9% / 68.1% | 61.0% | +0.9% / +1.9% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 10102 | 10 | 6.6% / 8.4% / 9.8% | 8.5% | -0.8% / -0.1% / +0.4% | 42.2% / 56.4% / 63.8% | 53.4% | +1.6% / +3.0% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 14643 | 15 | 6.5% / 7.9% / 10.2% | 7.8% | -0.4% / +0.1% / +0.6% | 56.0% / 60.1% / 63.1% | 58.2% | +1.1% / +1.9% / +2.9% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 4.5% / 4.5% / 4.5% | 3.9% | +0.6% / +0.6% / +0.6% | 27.7% / 27.7% / 27.7% | 26.9% | +0.8% / +0.8% / +0.8% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 25161 | 25 | 7.0% / 8.1% / 9.3% | 8.1% | -0.4% / -0.1% / +0.3% | 55.9% / 59.7% / 62.8% | 57.2% | +1.8% / +2.5% / +3.2% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 83 | 1 | 4.8% / 4.8% / 4.8% | 3.0% | +1.9% / +1.9% / +1.9% | 2.4% / 2.4% / 2.4% | 4.9% | -2.5% / -2.5% / -2.5% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 292 | 1 | 1.0% / 1.0% / 1.0% | 1.2% | -0.2% / -0.2% / -0.2% | 35.3% / 35.3% / 35.3% | 34.0% | +1.2% / +1.2% / +1.2% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 375 | 1 | 1.9% / 1.9% / 1.9% | 1.6% | +0.3% / +0.3% / +0.3% | 28.0% / 28.0% / 28.0% | 27.6% | +0.4% / +0.4% / +0.4% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 6405, MARK_UNAVAILABLE 3189
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
| DOWN | 5 | 2 | 2 | -360.7 | n/a | 0.0 | SECONDARY |
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
| AMBIGUOUS | 372 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 2662 | 1730 | 1348 | 1023 | 763 | 525 | 483 | 388 | 325 | 226 | 271 | 227 | 206 | 164 | 144 | 149 | 153 | 120 | 88 | 72 |
| TARGET_FIRST | 563 | 251 | 193 | 156 | 85 | 64 | 52 | 42 | 63 | 34 | 43 | 25 | 22 | 13 | 4 | 14 | 15 | 12 | 3 | 4 |

Caveats: 119 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
