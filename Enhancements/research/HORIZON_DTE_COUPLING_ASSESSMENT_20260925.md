# Horizon and DTE: can they depend on each other without moving the chosen contract?

**Date:** 2026-09-25 · **State:** research assessment, no authority, no pipeline change
**Question (ACK):** valuation must run on the time horizon; a trade that will not achieve its outcome inside 1–5 sessions should move to the correct horizon; can horizon and DTE be made dependent without impacting the DTE chosen?
**Evidence:** run `20260924_085940`, 401 GO / GO_LIMIT rows; spec v1.1 §9 (trade window) and §10 (last exit session); `scripts/avshunter_options_intelligence.py:1268-1330`; `domain/option_contract_liquidity.py:205-235`; `avshunter_discovery_ULTIMATE.py:2239`; harness `Enhancements/research/harness/merged_5_7_8_scenario_harness.py`

---

## 1. Short answer

Yes, and the governing design already does it. The coupling is one-directional: **DTE depends on the window, and the horizon depends on nothing but the evidence.** The contract is chosen to outlast the full 20-session window; which session the trade should actually exit is decided afterwards by valuing the *same* contract under several exit policies. The horizon is therefore an output of valuation, not an input to contract selection, and moving a trade to a different horizon never moves its contract.

The harness confirms this on the 24 September book: revaluing every actionable contract at 5, 10 and 20 sessions required a different contract in **0 of 401** cases, because every selected contract already carries at least 42 calendar days against a 40-day runway floor.

## 2. What the pipeline does today, and where the design is wrong

| Fact | Where | Consequence |
|---|---|---|
| `time_horizon` (1_5d / 6_10d / 11_20d) is assigned at Discovery from **signal quality**: Tier 0/1 or a strong trigger → 1_5d; Tier 2 or composite ≥ 45 → 6_10d; Tier 3 → 11_20d | `avshunter_discovery_ULTIMATE.py:2239-2262` | The bucket is a conviction label, not a timing forecast. Valuing on it is as wrong as valuing on 20 sessions; it just errs in the other direction |
| `planned_hold_sessions` = governed `outcome.window_sessions` = 20 on every row (`THESIS_WINDOW_D2`), regardless of bucket | `avshunter_options_intelligence.py:1268-1279` | The book plans the outer window, not the expected resolution. Under spec §9 that is correct for the window and silent on timing |
| DTE runway floor = 20 sessions + monitor + exit buffer = 40 calendar days (`minimum_required_dte` = 40 on all 401 rows); ACK 18 Sep decision (a): "the contract must outlast the planned hold (the thesis window), not only the anticipated move" | `contract_runway_policy`, `calculate_dte_requirement` | **Horizon and DTE are already decoupled.** The bucket "is kept in the basis for display and measurement and never shortens the runway" |
| The evidence timing fields the spec wants (`layer2__outcomes__median_days_to_target`, `layer2__raw_expected_time_to_target`) are **20.0 on all 401 rows** | Lab book | A constant is not evidence (Invariant B). There is currently no timing distribution to derive a horizon from |
| A second hold definition survives in the same file: `governed_dte_config` still reads `HORIZON_PLANNED_HOLD_SESSIONS = {1_5d: 5, 6_10d: 10, 11_20d: 20}` for the configured DTE band, while `contract_runway_policy` uses the 20-session window | `avshunter_options_intelligence.py:1238-1242, 1302-1330` | Two owners of "hold" in one module, the same dual-definition defect as the GARCH horizon fields (fix item F4) |

So the design error is not "20 instead of 5". It is that the horizon is a Discovery tier label on one side and a constant window on the other, and neither is a measured expected resolution.

## 3. What the specification prescribes (§9, §10)

- "There is **no fixed holding bucket** (no 5 / 10 / 20 choice) and no single `hold_sessions` value as a fundamental thesis variable. The expected holding duration is derived from the distribution of historical first-passage times." The thesis carries `expected_resolution_session`, `median_resolution_session` and quantiles, inside a fixed 1–20 window.
- Each expression carries an immutable `last_exit_session = min(Day 20, last session before expiry minus exit buffer)`. "A shorter-dated expression is not a shorter thesis."
- Expression generation produces **exit policies**: "base policy (target / invalidation / last_exit_session) plus approved time-stop variants (e.g. exit at Day N if unresolved)".
- "No weighted score of Greeks, delta bands or 'closest to expected resolution' may be used to pre-select contracts. Those are valuation questions."

That is exactly the mechanism ACK is asking for. The "correct horizon" for a trade is the exit-policy variant with the highest RAEV on the contract already chosen. A trade that will not resolve by Day 5 does not get re-routed to a different bucket; its Day-5 time-stop variant simply values below its Day-10 or Day-20 variant and the ranking says so.

## 4. The dependency, stated precisely

```
window            = 1..20 sessions                       (Thesis, fixed)
DTE floor         = runway(window + monitor + exit buffer)  (Expression; today 40 calendar days)
last_exit_session = min(Day 20, expiry − exit buffer)       (Expression; immutable per contract)
horizon           = argmax over exit policies {Day 5, Day 10, Day 20, base}
                    of RAEV(contract, policy | P(target-first by session k), P(invalidation-first by session k))
                                                            (Valuation + Ranking; an output)
```

Horizon depends on DTE only through `last_exit_session`, which caps the longest policy that can be valued. DTE depends on horizon **not at all**. That is the "dependent without impacting the DTE chosen" property, and it holds today because decision (a) pinned the runway to the window.

What the horizon needs and does not yet have is the session-indexed probability: `P(TARGET_FIRST by session k)` for k = 1..20 from the competing-risks estimator in method note 01. Fix item F1's outcome labels are precisely this curve. Without it, every exit policy is valued with the same probability and the longest policy wins mechanically.

## 5. Harness evidence (read-only, 24 September book)

Each of the 401 contracts was revalued, unchanged, under time-stop exit policies at 5, 10 and 20 sessions.

| Result | Value |
|---|---|
| Rows where any policy needed a different contract | 0 / 401 |
| Best policy by probability-free grid EV | Day 5: 202 · Day 20: 199 · Day 10: 0 |
| Best policy by ALG-07-shape utility with the row's legacy p | Day 20: 343 · Day 10: 28 · Day 5: 30 |
| Median utility gain from choosing the best policy over the assigned bucket | +14 points (p90 +32) |

Two readings:

1. **The mechanism works on the data as it is.** Exit policies can be valued on a fixed contract today, and the choice is material.
2. **The probability decides the horizon, and today's probability is horizon-blind.** The legacy `layer2__adjusted_prob_target_hit` is one number per row, applied identically at Day 5 and Day 20, so the longer policy collects the same probability against a larger reachable payoff and wins 343 times. The grid EV, which ignores direction probability, splits evenly between Day 5 and Day 20 because it trades reachable move against theta. Neither is a horizon forecast. Only a session-indexed first-passage curve can be.

## 6. What to change, in order

1. **Stop using the Discovery bucket as a timing input anywhere.** Keep `time_horizon` as a display label of signal tier and rename it so it cannot be read as a hold (fix item F4's units-in-names rule). The `HORIZON_PLANNED_HOLD_SESSIONS` band in `governed_dte_config` is the remaining consumer and should be retired in favour of the runway floor.
2. **Publish the first-passage curve per candidate geometry** (`P(target-first by session k)`, `P(invalidation-first by session k)`, k = 1..20, with n and censoring) from the Evidence context. This is F1's label writer with one extra dimension, the touch session. The constant-20 timing fields are replaced by `median_resolution_session` and quantiles read from that curve, or `TIMING_UNAVAILABLE`.
3. **Value each expression under the approved exit policies** (base + Day 5 / Day 10 / Day 20 time-stops) on the same contract, using the curve. The strongest expression becomes a (contract, exit policy) pair; the policy is the horizon.
4. **Leave DTE selection alone.** Decision (a) already makes the runway depend on the window. If ACK later wants a *maximum* DTE preference so the book does not pay for time it will not use, that belongs in valuation (theta shows up in the FLAT payoff) and in the generation band's `dte_max`, never as a pre-selection rule (§10 forbids "closest to expected resolution").
5. **Reassignment across horizons is then automatic.** A thesis that will not resolve by Day 5 shows a negative Day-5 policy and a better Day-10 or Day-20 policy on the same contract. No re-routing step is needed and nothing upstream is mutated (Invariant C).

## 7. Decisions needed from ACK

1. Confirm that the Discovery horizon bucket is a signal-quality label and not a hold, so it is removed from all valuation and DTE inputs.
2. Approve the exit-policy set to value (base + Day 5 / 10 / 20 is proposed; §10 says the set is versioned configuration).
3. Confirm decision (a) stands: DTE floor from the window, so horizon choice never changes the contract.

## 8. What the harness can run next without touching the pipeline

- Re-run the exit-policy comparison on earlier completed runs to see whether the Day-5 / Day-20 split is stable across books.
- Once F1 produces the first-passage curve for the phantom history, plug `P(target-first by k)` into the three policies and rerun. That is the first genuine horizon test.
