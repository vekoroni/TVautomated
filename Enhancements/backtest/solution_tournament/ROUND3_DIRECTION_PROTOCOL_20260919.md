# AVSHUNTER solution tournament — Round 3 direction protocol

**Frozen before opening the 2026 holdout:** 19 September 2026  
**Authority:** `EXPLORATORY_NO_AUTHORITY`

## Question

Can a point-in-time direction model improve the sign of the underlying move before option expression is considered?

## Data split

- Warm-up begins 1 September 2020.
- Train entry dates: 1 October 2021 through 29 November 2024.
- Embargo.
- Calibration/report-only dates: 15 January 2025 through 28 November 2025.
- Embargo.
- Sealed holdout entry dates: 15 January 2026 through the last session with the required forward horizon.
- Entry dates are sampled every five XNYS sessions. Forward labels are never used as features.
- Tradeable universe: close > $5 and trailing 20-session average dollar volume > $5 million.

## Point-in-time features

- 5- and 20-session return;
- 20-session relative strength versus SPY;
- 14-session ATR percentage and its trailing 252-session percentile;
- 20-session Bollinger width and its trailing 252-session percentile;
- compression score from the two past-only percentiles;
- current volume divided by the prior 20-session average;
- distance from the trailing 52-week high and low;
- SPY 5- and 20-session return as non-authoritative regime context.

## Pre-registered alternatives

- `CURRENT_H`: frozen AVSHUNTER CALL/PUT direction, evaluated only on H.
- `ALWAYS_CALL`: market-beta reference.
- `MOMENTUM_20`: CALL when trailing 20-session return is positive, otherwise PUT.
- `MEAN_REVERSION_5`: PUT after positive trailing 5-session return, otherwise CALL.
- `SPY_REGIME`: CALL when SPY trailing 20-session return is positive, otherwise PUT.
- `LOGISTIC_V1`: L2 logistic regression, C=0.1, trained only on the train split.
- `HGB_V1`: histogram gradient boosting, max leaf nodes 15, learning rate 0.05, max iterations 80, L2=1.0, trained only on the train split.

No model or threshold is tuned on the 2026 holdout. A fixed high-confidence subset is the top 20% of absolute probability distance from 0.5 inside each session.

## Outcomes

- raw signed underlying return at 1, 3, and 5 sessions;
- market-adjusted signed return;
- direction hit rate;
- session-block 90% confidence interval;
- Brier score and ROC AUC for probabilistic models;
- paired H comparison with the frozen pipeline direction.

## Promotion bar

This round may reject models but cannot promote one. Advancement requires consistent positive held-out signed return, improvement over unconditional and deterministic baselines, non-degenerate CALL/PUT mix, and later replication on additional certified sessions. Option results remain a separate expression-layer test.

