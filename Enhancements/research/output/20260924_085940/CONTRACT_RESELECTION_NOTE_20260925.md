# Contract re-selection by reachable-payoff expectancy — result

**Date:** 2026-09-25 · **State:** EXPLORATORY_NO_AUTHORITY · read-only on run `20260924_085940` · pipeline untouched
**Script:** `Enhancements/research/harness/contract_reselection_test.py` · **Output:** `contract_reselection_20260925T100832Z.csv`

## Test

For each of the 401 actionable rows, every contract in the run's `contracts_tested` record on the thesis side, at or above the 40-day window floor, with a two-sided quote inside the 30% friction domain, was valued with the merged 5+7+8 harness at the horizon hold (IV solved from mid for all, including the pipeline's own choice). Selection rule under test: highest probability-free grid EV. 367 rows had a valuable candidate set.

## Result

| Median | Pipeline's contract | Best by reachable-payoff expectancy |
|---|---|---|
| Spread, fraction of mid | 10.1% | 5.3% |
| Moneyness (strike / spot − 1) | +2.6% (OTM) | −3.4% (slightly ITM) |
| DTE | 57 | 57 |
| Grid EV at horizon hold | −10.8% | −4.7% |
| Reachable / |FLAT| asymmetry | 3.3 | 4.1 |

| Count over 367 rows | Value |
|---|---|
| Contract would change | 327 (89%) |
| Median EV gain where changed | +5.4 points |
| Rows with positive grid EV | 24 → 19 |
| Rows with asymmetry ≥ 2 and spread ≤ 15% | 261 → 284 |
| Better contract was rejected by the pipeline's `REJECT_DELTA_BAND` gate | 242 of 327 |
| On the 145 tickers with an `ESTIMATED_R_LT_1` rejection: changed / median gain / positive before → after | 133 / +5.4 points / 2 → 2 |

## Reading

1. **The delta band, not the R gate, is the contract-selection complexity kill.** 242 of the 327 better contracts exist in the tested chain and were excluded for being outside the delta band. The rule forces out-of-the-money contracts with wider spreads and more theta; the expectancy prefers near-the-money contracts with half the spread. Same DTE, same thesis.
2. **Re-selection halves the median loss but does not manufacture edge.** −10.8% becomes −4.7%; positive rows do not increase. The residual is the variance-risk premium plus a coin-flip direction. That is the correct result: expression cost is the first lever (it is worth 6 points a row), and probability is the second (it decides the sign).
3. **Asymmetry improves for the same reason.** 284 rows now sit above 2× with tight spreads, against 261 before, because the near-the-money contract loses less when nothing happens.
4. **The `ESTIMATED_R_LT_1` gate is doing something different from what its name says.** On the 145 affected actionable tickers the pipeline's choice is as bad as elsewhere and the gain from re-selection is the same; the gate is shaping routes, not protecting expectancy.

## What changes in the pipeline proposal

- P4 becomes: retire the delta band as a pre-selection gate as well as `ESTIMATED_R_LT_1`; generate the bounded set (§10) and let valuation choose. The spec already forbids delta bands as pre-selection ("No weighted score of Greeks, delta bands ... may be used to pre-select contracts").
- The 30–50 still depend on the probability (F1) and the forecast (ALG-10). Contract choice alone moves the median row from a 10.8% expected loss to a 4.7% expected loss; it does not cross zero.

## Limits

Scenario values, not returns; IV solved from mid; the tested-chain record is truncated on 102 of 1,339 tickers, so some better contracts may be missing from the candidate set, which biases the gain downward.
