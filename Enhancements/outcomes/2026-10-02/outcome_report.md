# Outcome report — as of 2026-10-02

Scorer `c12-outcome-scorer-v1.0.0` · base rate `c12-base-rate-v1.0.0` · conditions `c12-conditions-v1.0.0` · config snapshot `0cf80a4fff424d5f` · window 20 sessions · verdict requires ≥ 20 evidence sessions

Measurement only: nothing here changes a pipeline decision. Legacy predictions are scored as recorded. Condition labels are analysis dimensions only and never feed a gate, score or rank.

**How to read:** *Observed* is the cumulative incidence by session 20 (Aalen-Johansen, censoring respected). *Base* applies each prediction's own stop and target distances, in ATR units, to every ticker in the price store on the same evidence session and window (what chance entry would have done in the same market). *Excess* = observed − base with a session-block bootstrap interval; an interval wholly above zero for target (or below zero for stop) is evidence of skill, once the verdict column says OK.

## Coverage

- **provenance_class**: RECORDED_AT_RUN 38506, RETROSPECTIVE_UNVERIFIED 763
- **evidence_session_source**: DERIVED_FROM_RUN_ID 9965, RUN_META 2782, THESIS_ID 26522
- **invalidation_state**: MISSING 6141, VALID 33128
- **target_state**: INVALID_LEGACY 8452, LEVEL 24358, NONE 6459
- **contract_state**: MISSING 7706, SIDE_MISMATCH 1361, VALID 30202
- **direction**: BEAR 9789, BULL 26358, None 3122
- **base_state**: NOT_SCORABLE 5508, NO_ATR 12, None 1557, OK 32192
- **macro_freshness**: CURRENT 38576, STALE 693
- **outcome_state**: AMBIGUOUS 450, DATA_GAP 27, NOT_SCORABLE 5508, NOT_YET_SCORED 1557, OPEN_CENSORED 12621, STOP_FIRST 13920, TARGET_FIRST 2097, TIMEOUT 3089

Comparisons below include only predictions with both a scored outcome and a matched base rate.


## Legacy labels vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | ALL | 31486 | 29 | 7.2% / 8.1% / 9.3% | 8.2% | -0.4% / -0.1% / +0.2% | 53.6% / 57.1% / 60.2% | 55.4% | +1.1% / +1.7% / +2.3% | OK |
| headline | direction=BEAR | 7894 | 28 | 6.3% / 7.9% / 10.2% | 9.6% | -2.4% / -1.7% / -0.9% | 23.9% / 27.5% / 32.9% | 27.1% | -0.5% / +0.5% / +1.8% | OK |
| headline | direction=BULL | 23592 | 28 | 7.3% / 8.4% / 9.7% | 8.1% | -0.1% / +0.3% / +0.7% | 61.6% / 65.2% / 68.6% | 63.3% | +1.1% / +1.8% / +2.5% | OK |
| headline | ev3_absolute_state=INDETERMINATE | 11 | 5 | 0.0% / 0.0% / 0.0% | 17.2% | -19.3% / -17.2% / -8.8% | 25.0% / 49.2% / 77.8% | 34.3% | -5.5% / +14.9% / +39.2% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NEGATIVE_EV | 2613 | 11 | 9.7% / 11.9% / 15.4% | 12.6% | -2.1% / -0.7% / +0.4% | 48.6% / 52.1% / 59.0% | 49.9% | -2.2% / +2.2% / +9.5% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=NOT_APPLICABLE | 927 | 19 | 0.0% / 0.1% / 0.1% | 0.4% | -0.9% / -0.3% / -0.2% | 46.8% / 58.0% / 76.6% | 55.1% | -5.8% / +3.0% / +20.4% | INSUFFICIENT_SESSIONS |
| headline | ev3_absolute_state=UNVALIDATED | 18409 | 18 | 7.6% / 9.7% / 13.3% | 10.4% | -1.8% / -0.8% / +0.4% | 48.9% / 51.3% / 54.4% | 48.5% | +1.5% / +2.8% / +4.2% | INSUFFICIENT_SESSIONS |
| headline | final_action=BLOCK | 1967 | 15 | 6.5% / 12.4% / 25.0% | 13.2% | -2.4% / -0.9% / +3.2% | 52.6% / 55.6% / 71.2% | 50.7% | +0.5% / +4.9% / +14.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_NOW | 14 | 5 | 0.0% / 17.3% / 37.5% | 24.4% | -16.3% / -7.1% / +8.4% | 46.7% / 65.6% / 84.8% | 72.6% | -17.6% / -6.9% / +14.7% | INSUFFICIENT_SESSIONS |
| headline | final_action=BUY_SMALL | 397 | 11 | 2.0% / 5.3% / 7.9% | 8.3% | -6.9% / -3.1% / +1.1% | 30.2% / 37.9% / 63.6% | 53.6% | -17.6% / -15.7% / +1.6% | INSUFFICIENT_SESSIONS |
| headline | final_action=CONTRACT_REPAIR | 1002 | 16 | 0.0% / 0.1% / 0.1% | 0.9% | -3.1% / -0.7% / -0.2% | 35.2% / 49.3% / 56.9% | 50.0% | -7.3% / -0.7% / +7.0% | INSUFFICIENT_SESSIONS |
| headline | final_action=MANUAL_REVIEW | 18579 | 18 | 8.2% / 9.3% / 10.3% | 10.5% | -2.6% / -1.2% / -0.5% | 48.6% / 50.9% / 54.7% | 48.9% | -1.7% / +2.0% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=BLOCKED | 3066 | 23 | 5.9% / 9.4% / 20.4% | 9.8% | -2.2% / -0.3% / +1.8% | 53.2% / 60.7% / 69.3% | 58.0% | +0.6% / +2.6% / +5.0% | OK |
| headline | lab_verdict=CONTRACT_REPAIR | 1012 | 17 | 0.0% / 0.1% / 0.1% | 0.8% | -2.6% / -0.7% / -0.2% | 39.8% / 51.1% / 60.4% | 51.0% | -4.3% / +0.1% / +8.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO | 10 | 4 | 0.0% / 26.0% / 42.3% | 27.9% | -17.8% / -1.9% / +12.0% | 45.0% / 58.0% / 80.0% | 69.6% | -21.1% / -11.6% / +13.8% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=GO_LIMIT | 341 | 11 | 2.8% / 6.0% / 8.8% | 12.6% | -9.8% / -6.6% / -0.8% | 31.1% / 47.4% / 60.2% | 46.2% | -16.6% / +1.2% / +11.4% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MANUAL_REVIEW | 18577 | 18 | 8.2% / 9.3% / 10.3% | 10.5% | -2.6% / -1.2% / -0.5% | 48.6% / 50.9% / 54.7% | 48.9% | -1.7% / +2.0% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | lab_verdict=MORNING_VALIDATION_REQUIRED | 8480 | 8 | 6.8% / 8.0% / 9.5% | 7.8% | -0.4% / +0.2% / +0.8% | 56.9% / 61.3% / 64.8% | 59.6% | +0.8% / +1.7% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | target_state=INVALID_LEGACY | 7558 | 19 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 59.2% / 64.1% / 67.8% | 62.3% | +1.2% / +1.9% / +2.6% | INSUFFICIENT_SESSIONS |
| headline | target_state=LEVEL | 22662 | 27 | 11.9% / 13.9% / 16.9% | 14.2% | -0.9% / -0.3% / +0.5% | 51.5% / 53.2% / 55.9% | 51.8% | +0.5% / +1.5% / +2.6% | OK |
| headline | target_state=NONE | 1266 | 15 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 17.2% / 36.3% / 45.2% | 43.0% | -9.7% / -6.7% / +3.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=ACTIVE | 4748 | 12 | 5.6% / 7.2% / 9.2% | 10.8% | -5.1% / -3.5% / -0.4% | 44.3% / 49.3% / 53.7% | 52.3% | -11.0% / -3.0% / +4.1% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=DATA_INCOMPLETE | 161 | 12 | 0.0% / 0.0% / 0.0% | 0.0% | -0.0% / -0.0% / +0.0% | 0.8% / 60.1% / 73.2% | 30.2% | -3.1% / +29.9% / +30.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=INVALIDATED | 148 | 11 | 0.0% / 0.0% / 0.0% | 19.9% | -24.8% / -19.9% / -15.5% | 100.0% / 100.0% / 100.0% | 79.5% | +16.7% / +20.5% / +25.6% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=LEGACY_NOT_EVALUATED | 32 | 1 | 0.0% / 0.0% / 0.0% | 0.3% | -0.3% / -0.3% / -0.3% | 34.4% / 34.4% / 34.4% | 44.6% | -10.3% / -10.3% / -10.3% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=TARGET_REALIZED | 89 | 11 | 53.5% / 75.3% / 83.8% | 30.0% | +29.0% / +45.2% / +51.7% | 16.2% / 24.7% / 46.5% | 69.8% | -51.6% / -45.1% / -28.9% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_DATA_REVIEW | 31 | 13 | 0.0% / 0.0% / 0.0% | 1.8% | -7.3% / -1.8% / +0.0% | 8.7% / 19.1% / 31.9% | 31.7% | -27.1% / -12.6% / +0.2% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_READY | 160 | 10 | 3.6% / 13.7% / 36.3% | 5.7% | -0.7% / +8.0% / +28.3% | 26.9% / 43.7% / 50.5% | 44.8% | -19.7% / -1.2% / +8.4% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_REPAIR_AT_OPEN | 11147 | 16 | 7.8% / 9.7% / 13.6% | 10.0% | -1.4% / -0.3% / +2.3% | 52.2% / 55.6% / 58.5% | 53.0% | -0.8% / +2.6% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_TRIGGER_PENDING | 4990 | 16 | 8.3% / 10.2% / 14.4% | 12.0% | -2.9% / -1.8% / -0.6% | 39.3% / 42.1% / 51.3% | 40.6% | -1.4% / +1.5% / +10.0% | INSUFFICIENT_SESSIONS |
| headline | thesis_state=VALID_THESIS_WATCHLIST | 453 | 9 | 3.2% / 5.2% / 8.4% | 14.7% | -16.9% / -9.5% / -0.8% | 38.7% / 59.2% / 61.4% | 61.7% | -31.7% / -2.5% / +14.6% | INSUFFICIENT_SESSIONS |
| headline | tier=0 | 526 | 1 | 4.6% / 4.6% / 4.6% | 7.1% | -2.5% / -2.5% / -2.5% | 53.0% / 53.0% / 53.0% | 48.5% | +4.5% / +4.5% / +4.5% | INSUFFICIENT_SESSIONS |
| headline | tier=1 | 253 | 1 | 5.9% / 5.9% / 5.9% | 9.7% | -3.8% / -3.8% / -3.8% | 38.7% / 38.7% / 38.7% | 38.9% | -0.2% / -0.2% / -0.2% | INSUFFICIENT_SESSIONS |
| headline | tier=2 | 327 | 1 | 2.8% / 2.8% / 2.8% | 3.6% | -0.9% / -0.9% / -0.9% | 40.1% / 40.1% / 40.1% | 35.3% | +4.7% / +4.7% / +4.7% | INSUFFICIENT_SESSIONS |
| headline | tier=A | 6321 | 16 | 11.4% / 14.0% / 18.4% | 11.5% | +0.5% / +2.5% / +4.6% | 42.1% / 46.0% / 47.9% | 52.2% | -10.0% / -6.2% / -4.5% | INSUFFICIENT_SESSIONS |
| headline | tier=B | 3714 | 17 | 10.3% / 13.6% / 17.3% | 13.6% | -2.8% / -0.0% / +1.8% | 46.9% / 50.6% / 57.3% | 52.4% | -4.7% / -1.9% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | tier=C | 8445 | 17 | 6.2% / 8.1% / 14.7% | 10.1% | -3.5% / -2.0% / +3.5% | 53.7% / 56.3% / 66.5% | 48.3% | +6.9% / +8.0% / +16.5% | INSUFFICIENT_SESSIONS |
| headline | tier=WATCH | 2374 | 19 | 1.9% / 3.3% / 6.0% | 5.6% | -3.4% / -2.3% / -1.4% | 37.7% / 45.0% / 54.8% | 42.1% | -1.7% / +2.9% / +9.4% | INSUFFICIENT_SESSIONS |
| retrospective | ALL | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BEAR | 130 | 2 | 0.0% / 5.5% / 7.2% | 4.8% | -2.7% / +0.7% / +2.4% | 7.2% / 10.1% / 10.6% | 7.6% | -0.4% / +2.6% / +6.0% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL | 576 | 2 | 1.7% / 3.4% / 4.6% | 3.7% | -0.4% / -0.3% / +0.1% | 34.9% / 51.1% / 51.7% | 48.4% | +2.2% / +2.7% / +2.7% | INSUFFICIENT_SESSIONS |
| retrospective | ev3_absolute_state=UNVALIDATED | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BLOCK | 107 | 2 | 10.1% / 11.2% / 13.2% | 13.3% | -2.1% / -2.1% / +4.7% | 86.8% / 88.8% / 89.9% | 81.4% | -2.8% / +7.3% / +27.0% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_NOW | 5 | 2 | 0.0% / 0.0% / 0.0% | 2.6% | -4.2% / -2.6% / -0.2% | 0.0% / 20.0% / 33.3% | 29.3% | -9.3% / -9.3% / -7.2% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=BUY_SMALL | 96 | 2 | 1.5% / 4.8% / 4.8% | 3.0% | -0.9% / +1.8% / +1.8% | 16.7% / 35.7% / 43.3% | 38.0% | -2.3% / -2.3% / -0.3% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=CONTRACT_REPAIR | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 14.3% | -4.3% / -4.3% / +3.0% | INSUFFICIENT_SESSIONS |
| retrospective | final_action=MANUAL_REVIEW | 488 | 2 | 1.7% / 2.4% / 2.7% | 2.7% | -0.5% / -0.3% / +0.2% | 16.1% / 34.9% / 36.4% | 33.8% | -4.3% / +1.1% / +2.5% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=BLOCKED | 107 | 2 | 10.1% / 11.2% / 13.2% | 13.3% | -2.1% / -2.1% / +4.7% | 86.8% / 88.8% / 89.9% | 81.4% | -2.8% / +7.3% / +27.0% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=CONTRACT_REPAIR | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 14.3% | -4.3% / -4.3% / +3.0% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO | 5 | 2 | 0.0% / 0.0% / 0.0% | 2.6% | -4.2% / -2.6% / -0.2% | 0.0% / 20.0% / 33.3% | 29.3% | -9.3% / -9.3% / -7.2% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=GO_LIMIT | 96 | 2 | 1.5% / 4.8% / 4.8% | 3.0% | -0.9% / +1.8% / +1.8% | 16.7% / 35.7% / 43.3% | 38.0% | -2.3% / -2.3% / -0.3% | INSUFFICIENT_SESSIONS |
| retrospective | lab_verdict=MANUAL_REVIEW | 488 | 2 | 1.7% / 2.4% / 2.7% | 2.7% | -0.5% / -0.3% / +0.2% | 16.1% / 34.9% / 36.4% | 33.8% | -4.3% / +1.1% / +2.5% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=LEVEL | 697 | 2 | 3.0% / 3.9% / 4.0% | 4.0% | -0.3% / -0.1% / +0.2% | 32.0% / 43.2% / 43.2% | 40.6% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | target_state=NONE | 9 | 2 | 0.0% / 0.0% / 0.0% | 0.0% | +0.0% / +0.0% / +0.0% | 0.0% / 11.1% / 33.3% | 14.6% | -3.5% / -3.5% / +3.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=ACTIVE | 589 | 2 | 1.8% / 2.6% / 2.6% | 2.8% | -0.3% / -0.2% / -0.2% | 16.5% / 35.0% / 36.8% | 34.1% | -3.3% / +0.9% / +2.1% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=DATA_INCOMPLETE | 10 | 2 | 0.0% / 0.0% / 0.0% | 0.1% | -0.1% / -0.1% / +0.0% | 0.0% / 10.0% / 33.3% | 14.3% | -4.3% / -4.3% / +3.0% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=INVALIDATED | 91 | 2 | 0.0% / 2.2% / 3.2% | 13.1% | -10.9% / -10.9% / -7.3% | 96.8% / 97.8% / 100.0% | 81.3% | +9.9% / +16.5% / +32.9% | INSUFFICIENT_SESSIONS |
| retrospective | thesis_state=TARGET_REALIZED | 16 | 2 | 50.0% / 62.5% / 83.3% | 14.6% | +38.2% / +47.9% / +71.6% | 16.7% / 37.5% / 50.0% | 82.6% | -45.1% / -45.1% / -35.8% | INSUFFICIENT_SESSIONS |
| retrospective | tier=A | 319 | 2 | 4.3% / 6.1% / 6.1% | 4.6% | +0.7% / +1.6% / +1.8% | 25.6% / 43.0% / 45.7% | 42.8% | -0.4% / +0.3% / +0.3% | INSUFFICIENT_SESSIONS |
| retrospective | tier=B | 152 | 2 | 1.2% / 3.3% / 4.4% | 4.6% | -3.8% / -1.3% / +1.5% | 40.5% / 47.8% / 47.8% | 41.8% | +1.2% / +5.9% / +10.0% | INSUFFICIENT_SESSIONS |
| retrospective | tier=C | 213 | 2 | 1.6% / 1.9% / 3.7% | 2.9% | -3.2% / -1.0% / -0.6% | 39.2% / 41.1% / 44.4% | 38.1% | +2.7% / +2.9% / +3.5% | INSUFFICIENT_SESSIONS |
| retrospective | tier=WATCH | 22 | 2 | 0.0% / 0.0% / 0.0% | 2.3% | -2.8% / -2.3% / -0.2% | 35.3% / 48.9% / 48.9% | 34.3% | +9.8% / +14.6% / +14.6% | INSUFFICIENT_SESSIONS |

## Conditions vs matched base rate

| Scope | Group | Predictions | Sessions | Target observed (low / point / high) | Target base | Excess target (low / point / high) | Stop observed (low / point / high) | Stop base | Excess stop (low / point / high) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| headline | direction=BEAR x market_trend_state=ABOVE_BOTH | 6545 | 25 | 6.6% / 8.4% / 11.0% | 10.3% | -2.7% / -1.9% / -1.1% | 24.3% / 28.4% / 34.1% | 27.6% | -0.4% / +0.8% / +2.3% | OK |
| headline | direction=BEAR x market_trend_state=ABOVE_LONG_ONLY | 1349 | 3 | 4.0% / 6.5% / 7.3% | 5.6% | -0.7% / +0.9% / +1.6% | 18.8% / 28.2% / 46.1% | 27.7% | -0.4% / +0.5% / +5.8% | INSUFFICIENT_SESSIONS |
| headline | direction=BULL x market_trend_state=ABOVE_BOTH | 20646 | 25 | 6.5% / 7.5% / 8.5% | 7.3% | -0.3% / +0.1% / +0.5% | 63.9% / 67.3% / 70.3% | 65.3% | +1.3% / +2.0% / +2.8% | OK |
| headline | direction=BULL x market_trend_state=ABOVE_LONG_ONLY | 2946 | 3 | 13.2% / 14.0% / 14.8% | 12.8% | +0.8% / +1.2% / +1.6% | 47.2% / 52.2% / 53.9% | 51.9% | -0.8% / +0.3% / +1.5% | INSUFFICIENT_SESSIONS |
| headline | macro_freshness=CURRENT | 30813 | 28 | 7.0% / 7.9% / 8.8% | 7.9% | -0.4% / -0.1% / +0.2% | 53.7% / 57.2% / 60.5% | 55.7% | +1.0% / +1.5% / +2.0% | OK |
| headline | macro_freshness=STALE | 673 | 3 | 8.5% / 16.6% / 27.2% | 16.8% | -1.0% / -0.2% / +0.5% | 50.6% / 53.6% / 56.6% | 46.9% | +5.7% / +6.7% / +8.3% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=HIGH | 4515 | 4 | 5.8% / 6.9% / 8.0% | 7.0% | -0.5% / -0.1% / +0.3% | 60.8% / 63.6% / 66.1% | 62.0% | +1.0% / +1.6% / +2.1% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=LOW | 20528 | 14 | 6.5% / 7.9% / 8.8% | 7.8% | -0.4% / +0.2% / +0.4% | 42.9% / 45.1% / 46.3% | 46.3% | -2.5% / -1.2% / +0.5% | INSUFFICIENT_SESSIONS |
| headline | market_breadth_state=MID | 6443 | 11 | 7.7% / 10.2% / 13.5% | 9.8% | -0.4% / +0.4% / +1.2% | 52.4% / 58.9% / 64.3% | 56.6% | +0.9% / +2.2% / +3.6% | INSUFFICIENT_SESSIONS |
| headline | market_trend_state=ABOVE_BOTH | 27191 | 26 | 6.7% / 7.5% / 8.7% | 7.8% | -0.6% / -0.3% / +0.0% | 56.2% / 59.5% / 62.3% | 57.5% | +1.5% / +2.0% / +2.6% | OK |
| headline | market_trend_state=ABOVE_LONG_ONLY | 4295 | 3 | 10.0% / 11.3% / 12.4% | 10.5% | +0.6% / +0.8% / +1.1% | 40.0% / 44.4% / 47.1% | 44.5% | -0.2% / -0.1% / +0.9% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=HIGH | 3325 | 3 | 6.3% / 7.3% / 8.3% | 7.3% | -0.2% / +0.1% / +0.3% | 59.7% / 62.5% / 65.1% | 60.8% | +1.0% / +1.7% / +2.2% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=LOW | 15671 | 16 | 8.1% / 9.8% / 13.0% | 10.6% | -1.5% / -0.8% / +0.3% | 48.9% / 50.4% / 54.3% | 47.9% | +1.5% / +2.5% / +4.8% | INSUFFICIENT_SESSIONS |
| headline | market_vol_state=MID | 12490 | 10 | 5.9% / 7.2% / 8.7% | 7.2% | -0.5% / -0.1% / +0.5% | 56.5% / 62.3% / 66.9% | 60.4% | +1.0% / +1.9% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL | 2138 | 3 | 4.1% / 7.1% / 9.7% | 7.6% | -1.2% / -0.6% / +0.2% | 65.2% / 68.7% / 72.5% | 66.0% | +2.5% / +2.6% / +3.0% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BEARISH | 14705 | 13 | 7.1% / 8.5% / 9.6% | 8.6% | -0.9% / -0.2% / +0.3% | 46.2% / 52.9% / 59.4% | 51.7% | -0.1% / +1.2% / +2.5% | INSUFFICIENT_SESSIONS |
| headline | regime_label=TRANSITIONAL_BULLISH | 14643 | 15 | 6.6% / 7.9% / 9.8% | 7.9% | -0.5% / -0.0% / +0.4% | 54.8% / 58.3% / 61.4% | 56.7% | +0.9% / +1.6% / +2.7% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON | 1722 | 1 | 5.8% / 5.8% / 5.8% | 5.7% | +0.1% / +0.1% / +0.1% | 39.1% / 39.1% / 39.1% | 38.6% | +0.5% / +0.5% / +0.5% | INSUFFICIENT_SESSIONS |
| headline | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 29764 | 28 | 7.2% / 8.2% / 9.4% | 8.2% | -0.4% / -0.1% / +0.2% | 53.6% / 57.2% / 60.5% | 55.4% | +1.2% / +1.7% / +2.3% | OK |
| retrospective | direction=BEAR x market_trend_state=ABOVE_BOTH | 130 | 2 | 0.0% / 5.5% / 7.2% | 4.8% | -2.7% / +0.7% / +2.4% | 7.2% / 10.1% / 10.6% | 7.6% | -0.4% / +2.6% / +6.0% | INSUFFICIENT_SESSIONS |
| retrospective | direction=BULL x market_trend_state=ABOVE_BOTH | 576 | 2 | 1.7% / 3.4% / 4.6% | 3.7% | -0.4% / -0.3% / +0.1% | 34.9% / 51.1% / 51.7% | 48.4% | +2.2% / +2.7% / +2.7% | INSUFFICIENT_SESSIONS |
| retrospective | macro_freshness=CURRENT | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | market_breadth_state=LOW | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | market_trend_state=ABOVE_BOTH | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=LOW | 375 | 1 | 2.9% / 2.9% / 2.9% | 2.8% | +0.2% / +0.2% / +0.2% | 41.9% / 41.9% / 41.9% | 40.2% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| retrospective | market_vol_state=MID | 331 | 1 | 3.9% / 3.9% / 3.9% | 4.2% | -0.3% / -0.3% / -0.3% | 31.4% / 31.4% / 31.4% | 28.3% | +3.1% / +3.1% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BEARISH | 331 | 1 | 3.9% / 3.9% / 3.9% | 4.2% | -0.3% / -0.3% / -0.3% | 31.4% / 31.4% / 31.4% | 28.3% | +3.1% / +3.1% / +3.1% | INSUFFICIENT_SESSIONS |
| retrospective | regime_label=TRANSITIONAL_BULLISH | 375 | 1 | 2.9% / 2.9% / 2.9% | 2.8% | +0.2% / +0.2% / +0.2% | 41.9% / 41.9% / 41.9% | 40.2% | +1.6% / +1.6% / +1.6% | INSUFFICIENT_SESSIONS |
| retrospective | risk_on_off_switch=SELECTIVE_RISK_ON_REDUCED_SIZE | 706 | 2 | 2.9% / 3.9% / 3.9% | 3.9% | -0.3% / -0.1% / +0.2% | 31.4% / 43.0% / 43.0% | 40.3% | +1.6% / +2.7% / +3.1% | INSUFFICIENT_SESSIONS |

## Expressions: option contract vs underlying (headline predictions)

Entry at the recorded ask (else the chain ask on the evidence session; see entry_source), exit at the end-of-day bid on the exit session (underlying resolution, session-20 timeout, or the contract's last usable session). Underlying return is the same prediction's direction-signed return to its exit. Intervals: session-block bootstrap of the mean.

- **expression_state**: CONTRACT_INVALID 1423, ENTRY_NOT_VALUED 1845, MARKED 7761, MARK_UNAVAILABLE 5593
- **exit_reason (marked)**: CONTRACT_LAST_USABLE 840, RESOLUTION 6655, TIMEOUT 266

| Group | Marked | Sessions | Win rate (bid > ask) | Median return on premium | Mean return on premium (low / point / high) | Mean underlying return, same predictions | Verdict |
|---|---|---|---|---|---|---|---|
| ALL | 7761 | 27 | 12% | -53.6% | -46.8% / -43.8% / -40.5% | -2.1% | OK |
| direction=BEAR | 1481 | 27 | 25% | -37.5% | -27.1% / -20.9% / -15.2% | -2.6% | OK |
| direction=BULL | 6280 | 27 | 9% | -56.1% | -52.8% / -49.2% / -45.1% | -2.0% | OK |
| entry_source=CHAIN_ASK_EVIDENCE_SESSION | 222 | 3 | 20% | -73.4% | -45.3% / -41.9% / -41.2% | -0.3% | INSUFFICIENT_SESSIONS |
| entry_source=RECORDED_ASK | 7539 | 27 | 12% | -53.2% | -46.9% / -43.8% / -40.4% | -2.1% | OK |
| exit_reason=CONTRACT_LAST_USABLE | 840 | 10 | 27% | -62.7% | -43.1% / -29.3% / -20.3% | n/a | INSUFFICIENT_SESSIONS |
| exit_reason=RESOLUTION | 6655 | 27 | 9% | -53.3% | -50.8% / -47.0% / -42.8% | -2.3% | OK |
| exit_reason=TIMEOUT | 266 | 9 | 36% | -44.5% | -16.8% / -9.4% / -1.0% | +6.0% | INSUFFICIENT_SESSIONS |
| lab_verdict=BLOCKED | 1322 | 20 | 12% | -64.0% | -56.8% / -48.0% / -30.5% | -2.5% | OK |
| lab_verdict=CONTRACT_REPAIR | 24 | 4 | 25% | -58.9% | -82.9% / -39.3% / -11.3% | -3.4% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO | 5 | 3 | 20% | -30.8% | -25.6% / +13.1% / +29.7% | -0.3% | INSUFFICIENT_SESSIONS |
| lab_verdict=GO_LIMIT | 82 | 10 | 17% | -35.2% | -41.4% / -26.5% / -12.8% | -2.9% | INSUFFICIENT_SESSIONS |
| lab_verdict=MANUAL_REVIEW | 5621 | 17 | 10% | -51.2% | -47.5% / -44.8% / -42.3% | -2.3% | INSUFFICIENT_SESSIONS |
| lab_verdict=MORNING_VALIDATION_REQUIRED | 707 | 8 | 24% | -63.0% | -34.6% / -29.9% / -25.3% | +0.4% | INSUFFICIENT_SESSIONS |
| target_state=INVALID_LEGACY | 288 | 11 | 21% | -68.6% | -45.7% / -40.6% / -34.6% | -0.8% | INSUFFICIENT_SESSIONS |
| target_state=LEVEL | 7378 | 27 | 12% | -53.1% | -47.0% / -43.8% / -40.3% | -2.1% | OK |
| target_state=NONE | 95 | 4 | 21% | -82.5% | -86.2% / -46.3% / -44.5% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=0 | 262 | 1 | 5% | -68.2% | -61.8% / -61.8% / -61.8% | -3.1% | INSUFFICIENT_SESSIONS |
| tier=1 | 89 | 1 | 9% | -73.3% | -58.8% / -58.8% / -58.8% | -5.1% | INSUFFICIENT_SESSIONS |
| tier=2 | 109 | 1 | 5% | -84.2% | -71.0% / -71.0% / -71.0% | -4.2% | INSUFFICIENT_SESSIONS |
| tier=A | 1660 | 16 | 13% | -40.0% | -38.0% / -34.1% / -29.5% | -2.0% | INSUFFICIENT_SESSIONS |
| tier=B | 1439 | 17 | 15% | -45.2% | -42.5% / -38.0% / -33.6% | -1.7% | INSUFFICIENT_SESSIONS |
| tier=C | 2905 | 17 | 8% | -58.4% | -54.9% / -51.1% / -47.8% | -2.6% | INSUFFICIENT_SESSIONS |
| tier=WATCH | 450 | 17 | 10% | -65.7% | -62.4% / -54.3% / -49.3% | -2.6% | INSUFFICIENT_SESSIONS |
| underlying_state=AMBIGUOUS | 296 | 16 | 7% | -32.9% | -42.5% / -38.6% / -35.1% | -0.5% | INSUFFICIENT_SESSIONS |
| underlying_state=NOT_SCORABLE | 192 | 6 | 25% | -63.6% | -61.0% / -34.7% / -17.1% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=OPEN_CENSORED | 673 | 10 | 29% | -61.7% | -44.6% / -26.8% / -13.4% | n/a | INSUFFICIENT_SESSIONS |
| underlying_state=STOP_FIRST | 5284 | 27 | 0% | -61.4% | -66.7% / -61.5% / -56.7% | -4.3% | OK |
| underlying_state=TARGET_FIRST | 1075 | 27 | 54% | +5.4% | +14.4% / +22.5% / +32.1% | +6.6% | OK |
| underlying_state=TIMEOUT | 241 | 9 | 36% | -44.8% | -18.5% / -10.0% / -0.5% | +6.0% | INSUFFICIENT_SESSIONS |

## Forward hypothesis tests

`H9R_GAP_UP_REVERSAL` — pre-registered forward test from 2026-09-17 (SIGNAL_RESEARCH_PLAN_A.md Addendum 2). Primary: UP events, 10-session net return expected negative; verdict needs >= 30 event dates and >= 200 events, clustered t <= -2.0 and |mean| above the median share spread. Measurement only.

| Direction | Horizon | Events | Event dates | Mean net (bps) | Clustered t | Median share spread (bps) | Verdict |
|---|---|---|---|---|---|---|---|
| UP | 5 | 11 | 5 | -299.1 | n/a | 61.5 | SECONDARY |
| UP | 10 | 4 | 1 | 390.7 | n/a | 56.9 | INSUFFICIENT_EVIDENCE |
| UP | 20 | 0 | 0 | n/a | n/a | n/a | SECONDARY |
| DOWN | 5 | 8 | 6 | -117.3 | n/a | 0.0 | SECONDARY |
| DOWN | 10 | 2 | 2 | -22.3 | n/a | 0.0 | SECONDARY |
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
| AMBIGUOUS | 447 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| STOP_FIRST | 3203 | 2214 | 1627 | 1286 | 1004 | 706 | 680 | 546 | 441 | 324 | 333 | 264 | 252 | 202 | 182 | 166 | 165 | 137 | 108 | 80 |
| TARGET_FIRST | 621 | 294 | 233 | 186 | 118 | 92 | 68 | 57 | 94 | 70 | 77 | 43 | 34 | 29 | 12 | 28 | 17 | 14 | 5 | 5 |

Caveats: 121 groups compared (expect some intervals to exclude zero by chance); AMBIGUOUS counts as stop-first; TIMEOUT, OPEN_CENSORED and DATA_GAP are censored; the base-rate universe excludes tickers with a missing bar in the window; ticker sector is not yet recorded, so sector alignment is MISSING; macro conviction carries the DM-36 caveat.
