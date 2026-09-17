# 06 — Validation and Backtesting

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Gates: G3 Verification, G4 Validation · Capability: O7 Learning loop · Contexts: **C11 Decision Ledger, C12 Outcome, C13 Validation & Learning** · Governing: spec §15–§17, §23–§24

## Question this method answers

> How do we prove that a piece of logic achieves its objective on real data — without fooling ourselves — and when may it gain decision authority?

## 1. Two kinds of evidence

| Evidence | Source | Strength |
|---|---|---|
| **Historical (backtest / replication)** | Point-in-time replay of what the logic would have decided, through the production domain services | Fast, large sample; vulnerable to look-ahead, survivorship, overfitting |
| **Forward (live shadow)** | Records written to the ledger before outcomes are known | Slower; the only evidence free of hindsight |

Authority requires both: historical to design, forward to confirm.

## 2. Authority progression (spec §24)

```
BUILD (production-grade domain service)
   ↓
SHADOW / NON-AUTHORITATIVE
   ↓
REPLICATION through the same services (R1, R4, …)
   ↓
WALK-FORWARD and FORWARD SHADOW VALIDATION
   ↓
AUTHORITY (granted per context by ACK)
```

- A lightweight research replication may run earlier to de-risk a method; it does not replace replication through the production services.
- Every rule/model carries an authority state: `IMPLEMENTED_FOR_REPLICATION`, `NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY`, `SHADOW`, `AUTHORITATIVE`.
- Configuration values carry a `validation_state`; non-validated values drive shadow behaviour only (spec Appendix B).

## 3. Non-negotiable rules for historical tests

1. **Point-in-time inputs**: data as it was known at decision time (revisions, universe membership including delisted names, corporate actions, configuration versions in force).
2. **No look-ahead**: features use only trailing information; evidence packets use only what was observable by the evidence session (resolved events at their touch session; unresolved paths right-censored at their current age — spec AM-1); evaluation outcomes are scored only once observable.
3. **Purging and embargo**: remove training observations whose 20-session window overlaps the test period, and embargo a buffer after it (López de Prado, 2018, ch. 7 [verify]).
4. **Walk-forward**: fit on the past, test on the next period, roll forward; never tune on the full history.
5. **Realistic costs**: entry at ask, exit at bid with absolute spread floor, commissions, borrow — the same cost model as production.
6. **Same code path**: the backtest calls the production domain services with an injected clock and stored inputs (replay runner), not a separate re-implementation.
7. **Fresh, complete data**: replications run only on data that passes the C1 freshness and coverage gates.

## 4. Statistical honesty

- **Effective sample size**: count independent time blocks, not rows (note 01).
- **Multiple testing**: every variant tried (thresholds, states, geometry rules, bands) increases the chance of a false discovery. Record the number of trials. Use:
  - **Deflated Sharpe Ratio** (Bailey & López de Prado, 2014 [verify]);
  - **Probability of Backtest Overfitting (PBO)** via combinatorially symmetric cross-validation (Bailey, Borwein, López de Prado & Zhu [verify]);
  - higher significance thresholds for new factors (Harvey, Liu & Zhu, 2016 [verify]).
- **Uncertainty on every metric**: block bootstrap intervals.
- **Baseline comparison**: base rates for the same geometry distances, random expression within the same thesis, unconditional long option returns, nearest-target geometry.

## 5. Metrics by capability

| Capability | Primary metric | Secondary |
|---|---|---|
| Evidence probabilities and timing (O1) | Out-of-sample integrated Brier / log loss vs base rate; reliability of cumulative incidence at session checkpoints | Stability across refits; mirror symmetry |
| Direction state and geometry selection (O1) | Realised expectancy by state; R-H vs alternative geometry rules | Lift over base rate |
| EV (O2) | Realised expression P&L per $ at risk by predicted RAEV decile; calibration slope | Forced-exit accuracy; mean error; interval coverage |
| Expression choice and money location (O3) | Selected vs non-selected expressions of the same thesis; option vs share | Win share |
| Cheap convexity (O4) | Incremental return spread (cheap vs rich) after controlling for RAEV | Monotonicity |
| Ranking (O5) | Rank IC (Spearman) and decile spread, walk-forward | Deflated Sharpe of top-decile strategy; hysteresis cost |
| Morning decision (O6) | Realised vs revalued prediction for actioned expressions | Slippage vs model |
| Learning loop (O7) | % records with complete lineage and matured outcomes | Lag to maturity |
| Trustworthy operation (O8) | Capture coverage and freshness; replay identity | Run-health failures |

## 6. The decision ledger as the validation backbone (C11–C12)

Required for forward evidence:
- **Every context writes** its published output when produced: eligibility, structure and geometries, evidence packets, thesis versions (including `NOT_VALUED`, superseded), generated expressions (including exclusions), valuations (including `NOT_VALUED`, `NO_POSITIVE_EDGE`), books with every rank, execution decisions — each with an `actioned` flag and full lineage (run, release, clock, thesis/version, geometry, packet, expression, valuation, path set, book, window fields, `last_exit_session`, dataset/formula/configuration versions).
- **Underlying outcomes** for every thesis version (origin = evidence session; first touch by session within 1–20; `TARGET_FIRST` / `STOP_FIRST` / `TIMEOUT` / `AMBIGUOUS`).
- **Expression outcomes** for every valued expression, selected or not, actioned or not (origin = decision time; maturity at the earliest of resolution, `last_exit_session`, time stop; bid marks, P&L per $ at risk, MFE/MAE, IV change, spread cost, EV error).
- Deterministic, idempotent maturation keyed on record id with the injected clock.
- Journal fills linked by `thesis_id` / `expression_id`; test and smoke trades quarantined.

Without non-selected and non-actioned outcomes, ranking, selection and exclusion decisions cannot be validated.

## 7. Acceptance protocol (gate G4)

1. Pre-register the test: metric, pass threshold, sample window, number of variants tried.
2. Run historical walk-forward with costs through the production services; report metric with intervals, deflated statistics, PBO where applicable.
3. Run forward shadow for a minimum period (e.g. ≥ 60 sessions or ≥ N matured records per decile — to agree).
4. Independent review of results (human quant reviewer).
5. Grant authority per context only if both historical and forward evidence pass; record the decision, change the authority state, and schedule re-validation.

## Pitfalls (seen in AVSHUNTER today)

| Pitfall | Where observed |
|---|---|
| Acceptance = code matches spec | Fix programmes AVS-FIX-001/002 |
| No outcome linkage | Ledger `planned_hold_sessions` null on all candidates; 0 fit-eligible outcomes; journal trades without `thesis_id` |
| Only actionable rows considered for outcomes; option leg absent | Ledger / `doi_outcome_labels` 0 rows |
| Wall-clock dependence in replay | Discovery decay, EIL mode, maturation as-of |
| Separate research re-implementations | Audit scripts vs production modules |
| Tests on synthetic complete inputs only | 226 test files, none on real runs or missing inputs |
| Stale inputs used silently | Phantom history last session 2026-09-04; GEX COMPLETE on 10-day-old data |

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley — purged k-fold, embargo, backtest overfitting [verify]
- Bailey, D. & López de Prado, M. (2014). The deflated Sharpe ratio. *Journal of Portfolio Management* [verify]
- Bailey, D., Borwein, J., López de Prado, M. & Zhu, Q. (2017). The probability of backtest overfitting. *Journal of Computational Finance* [verify]
- Harvey, C., Liu, Y. & Zhu, H. (2016). …and the cross-section of expected returns. *Review of Financial Studies* [verify]
- White, H. (2000). A reality check for data snooping. *Econometrica* [verify]
- Graf, E. et al. (1999). Integrated Brier score for survival predictions. *Statistics in Medicine* [verify]
