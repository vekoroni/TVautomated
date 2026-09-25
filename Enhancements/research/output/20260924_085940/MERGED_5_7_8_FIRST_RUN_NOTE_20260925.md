# Merged Model 5 + 7 + 8 harness — first run on 20260924_085940

**State:** EXPLORATORY_NO_AUTHORITY · read-only against a completed run · harness `Enhancements/research/harness/merged_5_7_8_scenario_harness.py` v0.1
**Self-test:** reproduces the ALG-04 worked example (S 100, K 105, 30 DTE, σ 0.30, r 0.04) within 0.2 percentage points on all six scenarios.
**Scope:** the 401 GO / GO_LIMIT rows. All 401 valued; no row indeterminate; all spreads inside the friction model's domain.

## What was merged

| Model | Implementation in the harness |
|---|---|
| 5 Scenario repricing | ALG-04 grid FLAT / 1σ / 2σ / REACHABLE (k = 1.5) / STRUCTURAL / INVALIDATION at the LATE timing, IV stresses 0.8 / 1.0 / 1.2, BSM at the contract IV, vol budget = forecast vol × √(hold/252), bias multiplier 1.0 UNVALIDATED |
| 7 Execution friction | Entry at ask; exit at theoretical × (1 − min(spread/2, 0.15)) |
| 8 Decision | (a) probability-free: seven-point lognormal grid weighted by the normal density, EV and P(positive net exit); (b) ALG-07 shape using the row's `layer2__adjusted_prob_target_hit` as p_T with the residual split evenly between invalidation and timeout, labelled UNVALIDATED |

## Results, two hold conventions

| Median over 401 rows | Hold = book `planned_hold_sessions` (20 on every row, source THESIS_WINDOW_D2) | Hold = horizon bucket (5 or 10) |
|---|---|---|
| FLAT net return | −50.7% | −28.4% |
| 1σ net return | +57.0% | +24.2% |
| REACHABLE net return | +125.7% | +56.2% |
| STRUCTURAL net return | +193.7% | +209.2% |
| INVALIDATION net return | −86.7% | −69.4% |
| Grid EV (probability-free) | −17.3% | −17.7% |
| Grid EV p10 / p90 | −33.8% / +7.0% | −30.7% / −2.9% |
| P(positive net exit), grid | 30.1% | 30.1% |
| Rows with grid EV > 0 | 60 | 31 |
| ALG-07-shape utility with row p_T | +4.9% | −8.7% |
| Spread fraction of mid | 9.5% | 9.5% |
| IV − forecast vol | +0.5 pts; 54% of rows have IV above forecast | same |

## Readings

1. **Friction and time decay dominate.** With direction probability at 0.5, the median contract loses 17–18% of premium over the hold after costs under either convention. This is the variance-risk-premium fact from method note 04 §5 in the book's own numbers.
2. **The structural target is not the reachable target.** Median gap between the structural and reachable scenario is 63 points (20-session hold) and 135 points (horizon hold). Any number headlined from the structural target overstates what the vol budget says is reachable. This is F2 in the fix review, now quantified.
3. **The book's hold convention matters.** `planned_hold_sessions` is 20 on every row, including the 246 rows whose horizon bucket is 1–5 days. Under the 20-session hold, more rows turn positive (60 vs 31) because the vol budget grows with √hold while the contract IV stays fixed. Which convention is authoritative is a thesis-window question for the Thesis context, not for valuation.
4. **The positive rows are the forecast-above-IV rows.** The 60 grid-positive rows have median IV − forecast of −7.8 points versus +1.2 for the rest, and a vol budget nearly twice as large. The top row (VKTX CALL) has forecast vol 42 points above IV and a row p_T of 0.04. This is precisely the AVS-RANK-001 §4 concern: until ALG-10 validates the forecast, a positive grid EV may be a forecast artefact rather than cheap convexity.
5. **The row-carried probability changes the sign.** Using `layer2__adjusted_prob_target_hit` (median 0.35, range 0.18–0.52) the ALG-07-shape utility is +4.9% at the 20-session hold and −8.7% at the horizon hold. That probability is uncalibrated, so neither sign is evidence. It shows how much F1 (calibration) decides.
6. **58 of the 60 grid-positive rows are CALLs.** Direction asymmetry is worth a look under Invariant D once probabilities exist; at this stage it reflects IV skew and where the forecasts sit.

## What this run does not show

- No realised outcomes; nothing here is a return. It is the scenario valuation the pipeline should be publishing beside `rr_predicted`, run once on one book.
- The pricer is a replica with r = 0.04 and q = 0. Rates and dividends are defaulted in the pipeline too (note 07).
- p_T is the legacy layer-2 probability, not ALG-09 output.

## Next runs the harness supports without touching the pipeline

- `--scope ALL` to value the 1,131 non-actionable rows and see where the blocked book sits.
- Earlier completed runs via `--run-id` to test stability of the positive set across sessions.
- Once the ALG-10 report exists, a bias multiplier on the vol budget (one-line change) to test how many positive rows survive.
