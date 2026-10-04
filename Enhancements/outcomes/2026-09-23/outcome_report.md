# Outcome report — as of 2026-09-23

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 28720, RETROSPECTIVE_UNVERIFIED 414
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 1288, THESIS_ID 17881
- **invalidation_state**: MISSING 3873, VALID 25261
- **target_state**: INVALID_LEGACY 8038, LEVEL 16737, NONE 4359
- **contract_state**: MISSING 6178, SIDE_MISMATCH 1361, VALID 21595
- **direction**: BEAR 7142, BULL 20356, None 1636
- **base_state**: NOT_SCORABLE 3498, NO_ATR 11, None 1532, OK 24093
- **macro_freshness**: CURRENT 28441, STALE 693
- **outcome_state**: AMBIGUOUS 238, DATA_GAP 27, NOT_SCORABLE 3498, NOT_YET_SCORED 1532, OPEN_CENSORED 9559, STOP_FIRST 9937, TARGET_FIRST 1496, TIMEOUT 2847

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 23718 | 24 | 7.0% / 8.2% / 9.5% | 8.2% | -0.4% / +0.0% / +0.4% | 56.9% / 60.6% / 63.7% | 57.9% | +1.9% / +2.7% / +3.6% | OK |
| headline | direction=BEAR | 5896 | 23 | 5.9% / 7.8% / 10.3% | 8.9% | -2.0% / -1.1% / -0.1% | 32.9% / 37.3% / 43.2% | 34.6% | +1.0% / +2.7% / +4.3% | OK |
| headline | direction=BULL | 17822 | 23 | 7.1% / 8.5% / 10.0% | 8.3% | -0.2% / +0.2% / +0.7% | 61.1% / 65.7% / 70.1% | 63.2% | +1.7% / +2.6% / +3.6% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 8 | 3 | 0.0% / 0.0% / 0.0% | 14.0% | -15.9% / -14.0% / -10.5% | 27.3% / 37.5% / 60.0% | 25.3% | +6.1% / +12.2% / +25.9% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 1644 | 9 | 6.7% / 11.0% / 15.8% | 15.4% | -7.4% / -4.4% / +1.4% | 43.5% / 89.0% / 93.1% | 50.9% | +2.8% / +38.1% / +41.1% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 880 | 14 | 0.0% / 0.0% / 0.0% | 0.1% | -0.2% / -0.1% / -0.0% | 54.3% / 69.4% / 82.7% | 56.7% | -0.3% / +12.7% / +26.0% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 11660 | 13 | 6.6% / 9.5% / 13.9% | 14.1% | -5.1% / -4.7% / -0.3% | 43.9% / 58.3% / 60.2% | 46.7% | +4.7% / +11.6% / +12.4% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1856 | 11 | 5.7% / 12.2% / 25.6% | 15.6% | -4.5% / -3.4% / +4.0% | 43.8% / 52.9% / 74.8% | 47.3% | -0.6% / +5.6% / +24.8% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 4 | 2 | 0.0% / 25.0% / 33.3% | 25.5% | -12.0% / -0.5% / +6.9% | 0.0% / 75.0% / 75.0% | 72.5% | -49.6% / +2.5% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 118 | 7 | 0.0% / 3.7% / 13.0% | 11.4% | -8.9% / -7.7% / -0.6% | 20.9% / 65.8% / 75.1% | 53.1% | -3.2% / +12.8% / +13.9% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 935 | 11 | 0.0% / 0.0% / 0.0% | 2.0% | -4.3% / -2.0% / -0.0% | 46.6% / 60.8% / 67.6% | 53.0% | +5.1% / +7.8% / +15.5% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 11278 | 13 | 7.4% / 9.3% / 12.3% | 13.5% | -5.0% / -4.2% / -0.3% | 43.9% / 78.1% / 79.5% | 49.1% | +4.6% / +29.0% / +30.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 2868 | 19 | 5.7% / 9.2% / 20.7% | 9.3% | -3.7% / -0.0% / +1.9% | 53.0% / 63.8% / 69.1% | 61.5% | +0.1% / +2.3% / +4.9% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=CONTRACT_REPAIR | 945 | 12 | 0.0% / 0.0% / 0.0% | 1.5% | -3.8% / -1.5% / -0.0% | 53.8% / 81.0% / 84.7% | 62.7% | +6.8% / +18.3% / +21.3% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 4 | 2 | 0.0% / 25.0% / 33.3% | 25.5% | -12.0% / -0.5% / +6.9% | 0.0% / 75.0% / 75.0% | 72.5% | -49.6% / +2.5% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 143 | 8 | 0.0% / 8.0% / 14.0% | 17.5% | -11.9% / -9.4% / -2.1% | 29.1% / 61.8% / 69.4% | 45.8% | +3.4% / +16.0% / +20.8% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 11278 | 13 | 7.4% / 9.3% / 12.3% | 13.5% | -5.0% / -4.2% / -0.3% | 43.9% / 78.1% / 79.5% | 49.1% | +4.6% / +29.0% / +30.0% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 60.1% / 64.8% / 68.5% | 62.9% | +1.3% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 15126 | 22 | 16.6% / 19.1% / 23.2% | 19.2% | -1.1% / -0.1% / +0.9% | 54.5% / 57.0% / 59.0% | 53.6% | +2.0% / +3.4% / +4.7% | OK |
| headline | target_state=NONE | 1034 | 10 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 38.6% / 63.3% / 64.8% | 43.6% | +2.3% / +19.7% / +23.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 3465 | 8 | 3.7% / 9.9% / 11.8% | 14.3% | -7.0% / -4.4% / -0.8% | 38.8% / 76.9% / 82.3% | 52.5% | +5.7% / +24.4% / +24.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 130 | 8 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 1.3% / 73.2% / 79.4% | 37.5% | -0.1% / +35.7% / +36.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 73 | 7 | 0.0% / 0.0% / 0.0% | 24.5% | -29.6% / -24.5% / -18.6% | 100.0% / 100.0% / 100.0% | 74.9% | +19.2% / +25.1% / +30.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.2% | -0.2% / -0.2% / -0.2% | 31.2% / 31.2% / 31.2% | 35.0% | -3.7% / -3.7% / -3.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 69 | 7 | 76.5% / 85.5% / 88.9% | 32.3% | +47.8% / +53.3% / +58.5% | 11.1% / 14.5% / 23.5% | 67.5% | -57.9% / -53.0% / -47.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 20 | 8 | 0.0% / 0.0% / 0.0% | 2.0% | -6.0% / -2.0% / +0.0% | 10.0% / 45.5% / 100.0% | 35.2% | -20.5% / +10.2% / +48.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 52 | 5 | 0.0% / 25.0% / 63.0% | 5.6% | -0.8% / +19.4% / +51.5% | 8.3% / 14.8% / 21.4% | 29.4% | -21.9% / -14.6% / +0.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 7236 | 11 | 7.1% / 9.1% / 12.5% | 12.6% | -4.4% / -3.5% / -0.0% | 47.3% / 57.3% / 58.7% | 49.8% | +2.8% / +7.4% / +8.7% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 2996 | 11 | 6.3% / 11.1% / 18.2% | 15.7% | -5.1% / -4.5% / +0.6% | 37.9% / 49.6% / 53.9% | 39.7% | +3.2% / +9.9% / +13.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 118 | 4 | 2.4% / 23.6% / 89.4% | 23.8% | -39.1% / -0.2% / +40.4% | 0.0% / 15.0% / 16.0% | 62.7% | -56.0% / -47.7% / -4.9% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 2.9% / 2.9% / 2.9% | 5.6% | -2.7% / -2.7% / -2.7% | 45.4% / 45.4% / 45.4% | 39.3% | +6.2% / +6.2% / +6.2% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 2.8% / 2.8% / 2.8% | 6.5% | -3.7% / -3.7% / -3.7% | 34.4% / 34.4% / 34.4% | 30.5% | +3.9% / +3.9% / +3.9% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 1.2% / 1.2% / 1.2% | 2.2% | -1.0% / -1.0% / -1.0% | 30.3% / 30.3% / 30.3% | 24.4% | +5.9% / +5.9% / +5.9% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 2756 | 11 | 9.0% / 11.5% / 15.5% | 14.5% | -4.6% / -3.0% / +2.9% | 37.6% / 45.6% / 57.8% | 50.1% | -10.7% / -4.5% / +7.8% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 2243 | 12 | 10.4% / 15.5% / 19.8% | 17.6% | -3.1% / -2.1% / +3.1% | 39.5% / 54.7% / 59.5% | 49.9% | -5.0% / +4.8% / +7.7% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 6205 | 12 | 6.0% / 8.4% / 12.9% | 13.4% | -5.4% / -4.9% / -0.8% | 47.6% / 66.9% / 69.2% | 46.7% | +7.5% / +20.2% / +21.1% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 1882 | 14 | 2.5% / 4.3% / 8.6% | 6.8% | -3.9% / -2.4% / +0.2% | 38.4% / 54.8% / 74.6% | 45.2% | -2.5% / +9.6% / +30.8% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 83 | 1 | 2.4% / 2.4% / 2.4% | 1.7% | +0.7% / +0.7% / +0.7% | 2.4% / 2.4% / 2.4% | 3.3% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 292 | 1 | 1.0% / 1.0% / 1.0% | 0.8% | +0.3% / +0.3% / +0.3% | 21.9% / 21.9% / 21.9% | 23.2% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 38 | 1 | 13.2% / 13.2% / 13.2% | 5.5% | +7.7% / +7.7% / +7.7% | 86.8% / 86.8% / 86.8% | 78.3% | +8.5% / +8.5% / +8.5% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.5% | -0.5% / -0.5% / -0.5% | 20.0% / 20.0% / 20.0% | 15.8% | +4.2% / +4.2% / +4.2% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 17.3% | +16.0% / +16.0% / +16.0% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 302 | 1 | 0.0% / 0.0% / 0.0% | 0.5% | -0.5% / -0.5% / -0.5% | 8.6% / 8.6% / 8.6% | 11.7% | -3.1% / -3.1% / -3.1% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 38 | 1 | 13.2% / 13.2% / 13.2% | 5.5% | +7.7% / +7.7% / +7.7% | 86.8% / 86.8% / 86.8% | 78.3% | +8.5% / +8.5% / +8.5% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 17.3% | +16.0% / +16.0% / +16.0% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 2 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / -0.1% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 30 | 1 | 0.0% / 0.0% / 0.0% | 0.5% | -0.5% / -0.5% / -0.5% | 20.0% / 20.0% / 20.0% | 15.8% | +4.2% / +4.2% / +4.2% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 302 | 1 | 0.0% / 0.0% / 0.0% | 0.5% | -0.5% / -0.5% / -0.5% | 8.6% / 8.6% / 8.6% | 11.7% | -3.1% / -3.1% / -3.1% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 372 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.5% / 17.5% / 17.5% | 18.8% | -1.3% / -1.3% / -1.3% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 17.3% | +16.0% / +16.0% / +16.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 334 | 1 | 0.0% / 0.0% / 0.0% | 0.5% | -0.5% / -0.5% / -0.5% | 9.6% / 9.6% / 9.6% | 12.0% | -2.4% / -2.4% / -2.4% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 3 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 33.3% / 33.3% / 33.3% | 17.3% | +16.0% / +16.0% / +16.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 28 | 1 | 0.0% / 0.0% / 0.0% | 3.4% | -3.4% / -3.4% / -3.4% | 100.0% / 100.0% / 100.0% | 75.2% | +24.8% / +24.8% / +24.8% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 10 | 1 | 50.0% / 50.0% / 50.0% | 11.3% | +38.7% / +38.7% / +38.7% | 50.0% / 50.0% / 50.0% | 87.1% | -37.1% / -37.1% / -37.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 116 | 1 | 1.7% / 1.7% / 1.7% | 1.2% | +0.5% / +0.5% / +0.5% | 21.6% / 21.6% / 21.6% | 21.8% | -0.3% / -0.3% / -0.3% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 68 | 1 | 1.5% / 1.5% / 1.5% | 1.2% | +0.3% / +0.3% / +0.3% | 22.1% / 22.1% / 22.1% | 19.9% | +2.1% / +2.1% / +2.1% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 186 | 1 | 1.1% / 1.1% / 1.1% | 0.8% | +0.3% / +0.3% / +0.3% | 13.4% / 13.4% / 13.4% | 16.6% | -3.2% / -3.2% / -3.2% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 5 | 1 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / -0.0% | 20.0% / 20.0% / 20.0% | 10.9% | +9.1% / +9.1% / +9.1% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 4547 | 20 | 6.0% / 8.3% / 11.4% | 9.7% | -2.4% / -1.4% / -0.3% | 33.6% / 38.2% / 44.4% | 35.5% | +0.8% / +2.7% / +4.5% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 2.0% / 4.2% / 4.6% | 3.7% | -1.5% / +0.6% / +0.9% | 17.5% / 44.1% / 56.0% | 40.2% | +1.2% / +3.9% / +4.7% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 14876 | 20 | 6.4% / 7.6% / 9.0% | 7.4% | -0.3% / +0.2% / +0.8% | 63.3% / 67.8% / 71.7% | 65.4% | +1.5% / +2.4% / +3.5% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 10.4% / 12.8% / 14.4% | 12.5% | -0.3% / +0.3% / +1.2% | 45.0% / 50.8% / 52.2% | 48.8% | +0.1% / +2.0% / +4.4% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 23045 | 23 | 6.8% / 7.8% / 9.0% | 7.8% | -0.4% / +0.0% / +0.5% | 57.0% / 60.8% / 64.0% | 58.2% | +1.8% / +2.6% / +3.3% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 6.9% / 14.5% / 24.6% | 17.4% | -3.5% / -3.0% / +0.1% | 42.9% / 54.4% / 56.3% | 45.2% | +6.5% / +9.2% / +9.2% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 12760 | 9 | 4.0% / 5.8% / 7.0% | 6.1% | -1.1% / -0.3% / +0.2% | 36.5% / 39.9% / 40.3% | 36.4% | -2.0% / +3.5% / +4.7% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.6% / 10.0% / 13.2% | 9.4% | -0.3% / +0.6% / +1.5% | 52.6% / 59.4% / 65.0% | 57.3% | +0.8% / +2.1% / +3.6% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 19423 | 21 | 6.5% / 7.6% / 9.2% | 7.7% | -0.6% / -0.1% / +0.5% | 59.2% / 62.6% / 65.2% | 60.0% | +1.8% / +2.6% / +3.4% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 7.6% / 10.3% / 12.2% | 9.9% | +0.1% / +0.4% / +0.8% | 35.6% / 46.6% / 47.7% | 44.7% | +0.6% / +1.9% / +4.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 14192 | 15 | 6.6% / 9.2% / 12.8% | 13.3% | -4.6% / -4.1% / -0.1% | 46.9% / 59.5% / 73.2% | 47.5% | +6.2% / +12.0% / +26.3% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 6201 | 6 | 6.1% / 8.1% / 10.2% | 7.9% | -0.5% / +0.2% / +1.1% | 55.9% / 62.1% / 67.5% | 60.3% | +0.7% / +1.8% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 8429 | 9 | 6.3% / 8.2% / 9.7% | 8.4% | -0.9% / -0.2% / +0.4% | 43.6% / 57.5% / 65.5% | 53.8% | +2.3% / +3.7% / +6.6% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 13151 | 14 | 6.8% / 8.3% / 10.7% | 8.1% | -0.2% / +0.3% / +0.9% | 56.3% / 60.7% / 63.7% | 58.8% | +1.0% / +1.8% / +2.8% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 3.9% / 3.9% / 3.9% | 3.1% | +0.8% / +0.8% / +0.8% | 19.6% / 19.6% / 19.6% | 19.4% | +0.2% / +0.2% / +0.2% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 21996 | 23 | 7.0% / 8.1% / 9.5% | 8.2% | -0.5% / -0.0% / +0.4% | 56.8% / 60.5% / 63.6% | 57.8% | +1.9% / +2.8% / +3.6% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 83 | 1 | 2.4% / 2.4% / 2.4% | 1.7% | +0.7% / +0.7% / +0.7% | 2.4% / 2.4% / 2.4% | 3.3% | -0.9% / -0.9% / -0.9% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 292 | 1 | 1.0% / 1.0% / 1.0% | 0.8% | +0.3% / +0.3% / +0.3% | 21.9% / 21.9% / 21.9% | 23.2% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 375 | 1 | 1.3% / 1.3% / 1.3% | 1.0% | +0.4% / +0.4% / +0.4% | 17.6% / 17.6% / 17.6% | 18.8% | -1.2% / -1.2% / -1.2% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 5709, MARK_UNAVAILABLE 2574
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 840, RESOLUTION 4657, TIMEOUT 212

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 5709 | 22 | 13% | -57.1% | -47.9% / -44.3% / -40.5% | -1.9% | OK |
| direction=BEAR | 1267 | 22 | 25% | -42.4% | -29.9% / -22.6% / -15.6% | -2.9% | OK |
| direction=BULL | 4442 | 22 | 10% | -60.0% | -54.5% / -50.5% / -46.3% | -1.7% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 5487 | 22 | 13% | -56.6% | -48.1% / -44.4% / -40.4% | -2.0% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 840 | 10 | 27% | -62.7% | -43.1% / -29.3% / -20.3% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 4657 | 22 | 10% | -57.1% | -52.9% / -48.5% / -43.6% | -2.3% | OK |
| exit_reason=TIMEOUT | 212 | 6 | 35% | -45.5% | -25.0% / -11.3% / -0.5% | +6.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1181 | 17 | 12% | -65.2% | -58.2% / -49.9% / -34.5% | -2.6% | INSUFFICIENT_SESSIONS |
| lab_verdict=CONTRACT_REPAIR | 24 | 4 | 25% | -58.9% | -82.9% / -39.3% / -11.3% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 3 | 1 | 33% | -30.8% | +36.5% / +36.5% / +36.5% | -0.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 51 | 7 | 22% | -45.7% | -48.7% / -25.3% / -7.3% | -3.9% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 3743 | 12 | 11% | -54.1% | -49.4% / -45.6% / -42.6% | -2.2% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 282 | 11 | 21% | -67.4% | -44.7% / -39.9% / -32.1% | -0.3% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 5332 | 22 | 13% | -56.6% | -48.3% / -44.5% / -40.4% | -2.0% | OK |
| target_state=NONE | 95 | 4 | 21% | -82.5% | -86.2% / -46.3% / -44.5% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 244 | 1 | 5% | -66.1% | -60.3% / -60.3% / -60.3% | -2.9% | INSUFFICIENT_SESSIONS |
| tier=1 | 84 | 1 | 7% | -73.0% | -61.6% / -61.6% / -61.6% | -5.5% | INSUFFICIENT_SESSIONS |
| tier=2 | 94 | 1 | 1% | -83.3% | -76.9% / -76.9% / -76.9% | -4.3% | INSUFFICIENT_SESSIONS |
| tier=A | 944 | 11 | 14% | -42.5% | -39.5% / -35.8% / -31.2% | -2.2% | INSUFFICIENT_SESSIONS |
| tier=B | 1018 | 12 | 18% | -45.8% | -42.6% / -36.8% / -31.5% | -1.6% | INSUFFICIENT_SESSIONS |
| tier=C | 2095 | 12 | 8% | -60.0% | -56.6% / -51.4% / -47.4% | -2.4% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 383 | 12 | 12% | -66.5% | -63.4% / -53.4% / -48.1% | -2.3% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 214 | 14 | 7% | -35.9% | -44.2% / -39.3% / -34.7% | -0.6% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 167 | 6 | 22% | -66.3% | -65.9% / -39.3% / -22.6% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 673 | 10 | 29% | -61.7% | -44.6% / -26.8% / -13.4% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 3600 | 22 | 0% | -66.1% | -70.6% / -64.5% / -58.9% | -4.3% | OK |
| underlying_state=TARGET_FIRST | 843 | 22 | 51% | +1.7% | +8.3% / +17.6% / +29.8% | +5.8% | OK |
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
| AMBIGUOUS | 235 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 2299 | 1540 | 1201 | 916 | 642 | 464 | 470 | 365 | 292 | 193 | 253 | 223 | 200 | 159 | 141 | 147 | 153 | 119 | 88 | 72 |
| TARGET_FIRST | 501 | 243 | 186 | 144 | 77 | 47 | 44 | 41 | 55 | 25 | 30 | 24 | 21 | 12 | 4 | 12 | 12 | 11 | 3 | 4 |

Caveats: 119 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
