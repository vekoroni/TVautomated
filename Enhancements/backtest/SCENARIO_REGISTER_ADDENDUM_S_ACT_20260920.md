# Backtest scenario register addendum — S-ACT option activity evidence

**Registered:** 20 September 2026  
**Version:** 1.0  
**State:** `PRE-REGISTERED — NO RESULTS READ — NO PRODUCTION AUTHORITY`  
**Parent register:** `Enhancements/backtest/SCENARIO_REGISTER_20260919.md`  
**Parent SHA-256:** `52cf8ac6b50d288edffb86dfb487d5d0f47db05a24dc4923dddf916c07668dcc`

This addendum does not edit or supersede the frozen 19 September register. It
adds one scenario family requested after the F7 review established that
delta-weighted open interest is positioning concentration, not signed option
flow. Every execution of this family is a ledger trial. A definition change
creates a new scenario id/version; it must never overwrite a result already
observed under an earlier definition.

## 1. Business question

Can point-in-time option positioning and activity improve the probability of
selecting a monetisable long call or long put, or improve the decision to enter,
defer, monitor, or change contract, after controlling for option price, quoted
friction, contract geometry, ticker thesis and market regime?

The family does **not** ask whether a high put/call ratio is bearish or a low
ratio bullish. Aggregate OI and volume cannot reveal whether contracts were
bought, sold, opened, closed or used as hedges. The tests must preserve that
ambiguity unless additional point-in-time premium/IV evidence supports a
probabilistic interpretation.

## 2. Relationship to the parent register

| Parent item | S-ACT contribution |
|---|---|
| M7 — missing/delayed flow data | Measures exactly what the stored chain can and cannot establish |
| M16 — features never enter ranking | Tests incremental value before any authority is granted |
| M17 — entry timing | Tests whether activity evidence supports enter/defer/monitor decisions |
| M20 — buying expensive IV | Conditions activity evidence on IV price and IV change |
| M22 — flat/unused features | Tests continuous raw values, not only categorical labels |
| Layer A — Intelligence | Measures incremental information about direction, magnitude and timing |
| Layer B — Pricing | Tests whether apparent activity is already priced into IV/premium |
| Layer C — Expression | Tests contract-family ranking and entry state |
| Layer D — Management | Tests deferred confirmation and subsequent re-expression |

S-ACT runs after the frozen integration replay and feeds Batch E
(`Thesis-conditioned entry and path stress`). It cannot change the ticker
thesis, invalidate an opportunity, or delete a contract family.

## 3. Frozen definitions

### 3.1 Ratio states

For a non-negative put/call ratio `r`:

- `CALL_HEAVY` when `r < 0.70`;
- `BALANCED` when `0.70 <= r <= 1.00`;
- `PUT_HEAVY` when `r > 1.00`;
- `UNKNOWN` when the denominator is absent/non-positive or the value is not
  point-in-time usable.

These labels describe concentration. They are not CALL/PUT votes.

### 3.2 Required separations

- OI positioning and printed-volume activity remain separate raw dimensions.
- CALL and PUT populations are reported separately.
- Contract-level, expiry-level, delta-region and whole-chain features are never
  substituted silently for one another.
- Liquidity maturation and contract payoff are separate outcomes.
- Same-session evidence and next-session confirmation are separate decisions.
- Missing data remains missing; it is never converted to zero or neutral.

### 3.3 Prohibited inference

No S-ACT variant may claim buyer/seller-initiated flow without governed trade
prints matched to contemporaneous bid/ask evidence. No ratio can independently
confirm or contradict the governed thesis direction.

## 4. Scenario catalogue

All variants are evaluated on the same eligible rows as S-ACT-0. A variant may
abstain when its required observation is missing, but missing rows cannot be
scored as zero-return trades.

| Id | Frozen variant | Purpose |
|---|---|---|
| **S-ACT-0** | No PCR/OI activity feature. Current corrected advisory-only pipeline baseline. | Control |
| **S-ACT-1** | Whole-chain raw OI PCR (`put OI / call OI`). | Test unweighted positioning |
| **S-ACT-2** | Whole-chain absolute-delta-weighted OI PCR. | Test exposure-weighted positioning |
| **S-ACT-3** | Whole-chain printed-volume PCR (`put volume / call volume`), with no OI substitution. | Test same-session activity concentration |
| **S-ACT-4** | Two-dimensional OI/volume state: corroborated CALL-heavy, corroborated PUT-heavy, both balanced, mixed, positioning-only, volume-only, insufficient. | Test whether agreement adds information |
| **S-ACT-5** | PCR recomputed within the thesis-horizon-matched expiry set. No cross-expiry aggregation. | Remove expiry contamination |
| **S-ACT-6** | PCR recomputed inside `abs(delta) 0.20–0.60`; separately report near-ATM (`abs(moneyness) <= 2.5%`). | Test relevant contract region |
| **S-ACT-7** | S-ACT-4 plus point-in-time premium residual and IV change. Premium residual is observed option return less delta × underlying return over the observation interval. | Distinguish activity with price/volatility confirmation |
| **S-ACT-8** | Deferred decision only: S-ACT-7 plus OI change first observable after the next completed clearing session. | Test opening/closing confirmation without look-ahead |
| **S-ACT-9** | Combined model using the raw continuous S-ACT-1/2/3/5/6/7 inputs, missingness flags and uncertainty; benchmark logistic model first, nonlinear challenger second. | Test incremental combined information |

S-ACT-9 cannot be activated unless the simpler variants establish stable
incremental information. Its predictions remain research probabilities.

## 5. Populations and chronology

| Population | Use |
|---|---|
| **H** | Failure localisation and compatibility with the original frozen candidate book; never judges the fixed pipeline |
| **H+** | Primary historical daily activity/contract test after the 760-ticker backfill; explicitly selection-biased |
| **Weekly full universe** | Coarse but less selection-biased positioning/activity validation |
| **N** | Fixed-pipeline forward confirmation; required before promotion |

The explicit TEST/dirty run is excluded from primary estimates and may appear
only in a labelled sensitivity appendix. Adjacent rows for the same ticker and
session are not independent trials. Reporting must aggregate/cluster by session
and ticker as appropriate.

## 6. Point-in-time and leakage controls

1. Every input is bound to ticker, option symbol or declared aggregation scope,
   provider observation time, completed session and dataset id/hash.
2. S-ACT-0 through S-ACT-7 use only evidence observable at the decision time.
3. S-ACT-8 may be evaluated only as a **new deferred decision** after the next
   OI observation becomes available. It cannot be assigned to the original
   entry decision.
4. Daily OI is treated as clearing-lagged unless provider semantics establish a
   more precise timestamp.
5. A completed-session volume total cannot be used for a pre-close decision.
6. Historical `BULLISH/BEARISH` PCR labels are ignored and recomputed from raw
   ratios under this addendum.
7. Mutable IV caches are not outcome authority. Frozen chain observations and
   their dataset identities are authoritative.
8. Train/calibration/holdout periods follow the parent register. No holdout is
   opened while definitions or thresholds are being changed.

## 7. Outcomes and scorecards

### Layer A — information

- Forward underlying return in the governed direction at 1/3/5 sessions.
- Forward absolute move and expansion-event incidence.
- Incremental rank correlation and model-with/model-without improvement.
- CALL and PUT results separately and by regime.

### Layer B — price

- Realised move divided by implied move at entry.
- IV and risk-reversal change after the observation.
- Premium residual after delta-explained underlying movement.
- Evidence that the activity state was already priced.

### Layer C — monetisation/expression

- Ask-entry to bid-exit return at 1/3/5 sessions.
- Mid and timed fills as sensitivity only; quoted fills remain primary.
- Probability of positive return.
- MFE and MAE using executable bid marks.
- Contract-family rank, selected-contract dominance and alternative-contract
  performance.
- Liquidity maturation: executable within 1/2/3 sessions, minimum spread and
  first meaningful printed volume.

### Right tail — mandatory

- Share reaching +50/+100/+200/+500%.
- Time to each threshold.
- Tail opportunity recall across the full available contract family.
- Largest winner retained and tail contribution to total profit.

Mean improvement that destroys tail capture must be reported as a trade-off,
not a pass.

## 8. Stress matrix

Every S-ACT variant is run under:

- CALL and PUT populations separately;
- 1/3/5-session horizons;
- denominator floors of 1, 10 and the pre-registered liquidity-aware floor;
- uncapped, p01/p99 winsorised and log-ratio transforms;
- stale OI and one-session OI-lag simulations;
- 10% and 25% random activity-field dropout;
- all printed volume missing;
- low-OI developing contracts isolated, never deleted;
- whole-chain versus expiry-matched versus delta-region scopes;
- quoted spread widened by 25% and 50%;
- quote dropout of 10% and 25%;
- IV crush and expansion;
- overnight gap continuation and reversal;
- high/low volatility and SPY bull/bear regimes;
- removal of the best-performing 1%;
- leave-one-session-out validation.

The denominator floor is a numerical-stability sensitivity, not an eligibility
gate. No stress variant may discard the ticker thesis because activity evidence
is absent or adverse.

## 9. Comparisons and pass gates

Each variant is compared pairwise with S-ACT-0 on identical rows and dataset
hashes. It must also be compared with the preceding simpler variant to show
incremental value.

The parent-register gate applies:

- paired difference with `t >= 2.0` on the historical population;
- session-block bootstrap interval reported alongside the t-statistic;
- the same sign on N once N has at least 40 closed outcomes;
- useful participation reported rather than treating abstentions as zero;
- no future-data dependency;
- no material degradation of +100/+200/+500% recall;
- Probability of Backtest Overfitting and deflated Sharpe reported after at
  least 10 trials in this family.

A ratio or state may be useful for liquidity prediction while failing payoff
prediction. Such a result advances only the liquidity model; it cannot be
presented as evidence of monetisability or direction.

## 10. Batch E integration

Only variants surviving their own information/pricing tests are inserted into
Batch E. The frozen Batch E route remains:

```text
governed ticker thesis
  + required underlying move after spread, IV, theta and DTE
  + exact contract-family quote/geometry
  + eligible S-ACT evidence
  -> enter now / defer / monitor / alternative contract / no current expression
```

S-ACT evidence may help rank expressions or estimate a probability. It may not:

- reverse or invalidate the ticker thesis;
- create a hard OI/volume eligibility gate;
- suppress a developing contract from monitoring;
- grant execution or capital authority;
- describe aggregate ratios as institutional buying/selling.

## 11. Execution and evidence requirements

Before the first trial:

1. Freeze the corrected activity implementation in a commit or governed release
   manifest; record the exact dirty state if a commit is not yet possible.
2. Hash every input dataset and the parent/addendum documents.
3. Record scenario id/version, code commit, dirty state, configuration snapshot,
   population, fill model, horizon, stress variant and random seed.
4. Append every execution, including failed or empty trials, to the backtest
   ledger.
5. Keep exploratory diagnostics distinct from registered confirmatory results.
6. Publish row-level outputs sufficient to reproduce all aggregates.

## 12. Decision states

- `NO_EVIDENCE`: gate not met or insufficient observations.
- `LIQUIDITY_ONLY`: improves maturation/executability but not payoff.
- `PAYOFF_EVIDENCE`: improves monetisation but awaits N confirmation.
- `FORWARD_CONFIRMED`: historical gate and N gate both pass.
- `REJECTED`: materially worse or unstable after registered stress.

No state automatically authorises a production build. A passing result becomes
a separate solution-design proposal for review.
