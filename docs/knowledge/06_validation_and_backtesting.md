# 06 — Validation and Backtesting

Status: **Draft** · Gates: G3 Verification, G4 Validation · Capability: O7 Learning loop

## Question this method answers

> How do we prove that a piece of logic achieves its objective on real data — without fooling ourselves?

## 1. Two kinds of evidence

| Evidence | Source | Strength |
|---|---|---|
| **Historical (backtest)** | Point-in-time reconstruction of what the logic would have decided | Fast, large sample; vulnerable to look-ahead, survivorship, overfitting |
| **Forward (live shadow)** | Decisions recorded before outcomes are known (decision ledger) | Slower; the only evidence free of hindsight |

Authority requires both: historical to design, forward to confirm.

## 2. Non-negotiable rules for historical tests

1. **Point-in-time inputs**: data as it was known at decision time (revisions, universe membership including delisted names, corporate actions).
2. **No look-ahead**: features use only trailing information; labels mature after the decision; evidence packets built only from outcomes matured before the decision date.
3. **Purging and embargo**: when training and test periods are adjacent, remove training observations whose label horizon overlaps the test period, and embargo a buffer after it (López de Prado, 2018, ch. 7 [verify]).
4. **Walk-forward**: fit on the past, test on the next period, roll forward; never tune on the full history.
5. **Realistic costs**: entry at ask, exit at bid, commissions, borrow — the same cost model as production.
6. **Same code path**: the backtest calls the production domain services with an injected clock and stored inputs (replay runner), not a separate re-implementation.

## 3. Statistical honesty

- **Effective sample size**: count independent time blocks, not rows (note 01).
- **Multiple testing**: every variant tried (thresholds, states, horizons) increases the chance of a false discovery. Record the number of trials. Use:
  - **Deflated Sharpe Ratio** — adjusts a Sharpe ratio for number of trials and non-normal returns (Bailey & López de Prado, 2014 [verify]);
  - **Probability of Backtest Overfitting (PBO)** via combinatorially symmetric cross-validation (Bailey, Borwein, López de Prado & Zhu [verify]);
  - higher significance thresholds for new factors (Harvey, Liu & Zhu, 2016 [verify]).
- **Uncertainty on every metric**: block bootstrap confidence intervals.
- **Baseline comparison**: every model is compared with a naive baseline (base rates, random expression within the same thesis, unconditional long option returns).

## 4. Metrics by capability

| Capability | Primary metric | Secondary |
|---|---|---|
| Probabilities (O1) | Out-of-sample Brier / log loss vs base rate; reliability | Stability across refits |
| Direction state (O1) | Hit rate by state with Wilson CI | Lift over base rate |
| EV (O2) | Realised P&L per $ by predicted EV decile; calibration slope | Mean error, CI coverage |
| Expression choice (O3) | Chosen vs alternatives within thesis | Win share |
| Cheap convexity (O4) | Realised return spread top vs bottom quintile | Monotonicity |
| Ranking (O5) | Rank IC (Spearman) and decile spread, walk-forward | Deflated Sharpe of top-decile strategy |
| Morning decision (O6) | Realised vs revalued prediction for acted rows | Slippage vs model |
| Learning loop (O7) | % decisions with complete inputs and matured outcomes | Lag to maturity |

## 5. The decision ledger as the validation backbone

Required for forward evidence (fix before logic rebuild):
- One immutable record per decision with: thesis fields, hold, evidence packet id, expression set and valuations, rank, action, input dataset ids, formula versions, as-of clock.
- Deterministic maturation keyed on (decision, horizon) with the plan clock; underlying and option legs.
- Journal fills linked by `thesis_id` / expression id; test and smoke trades quarantined.

## 6. Acceptance protocol (gate G4)

1. Pre-register the test: metric, pass threshold, sample window, number of variants tried.
2. Run historical walk-forward with costs; report metric with CI, deflated statistics, PBO where applicable.
3. Run forward shadow for a minimum period (e.g. ≥ 60 sessions or ≥ N matured decisions per decile — to agree).
4. Independent review of results (human quant reviewer).
5. Grant authority only if both historical and forward evidence pass; record the decision and schedule re-validation.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Acceptance = code matches spec | Fix programmes AVS-FIX-001/002 |
| No outcome linkage | Ledger `planned_hold_sessions` null on all candidates; 0 fit-eligible outcomes; journal trades without `thesis_id` |
| Wall-clock dependence in replay | Discovery decay, EIL mode, maturation as-of |
| Separate research re-implementations | Audit scripts vs production modules |
| Tests on synthetic complete inputs only | 226 test files, none on real runs or missing inputs |

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley — purged k-fold, embargo, backtest overfitting [verify]
- Bailey, D. & López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio Management* [verify]
- Bailey, D., Borwein, J., López de Prado, M. & Zhu, Q. (2017). The probability of backtest overfitting. *Journal of Computational Finance* [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). …and the cross-section of expected returns. *Review of Financial Studies* [verify]
- White, H. (2000). A reality check for data snooping. *Econometrica* [verify]
