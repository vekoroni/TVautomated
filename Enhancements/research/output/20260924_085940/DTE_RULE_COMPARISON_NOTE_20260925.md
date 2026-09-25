# DTE from the anticipated move versus DTE from the window — measured difference

**Date:** 2026-09-25 · **State:** EXPLORATORY_NO_AUTHORITY · read-only against run `20260924_085940` · pipeline untouched
**Script:** `Enhancements/research/harness/dte_rule_comparison.py` · **Output:** `dte_rule_comparison_20260925T095349Z.csv`

## Rules compared

| Rule | Runway floor | Calendar days | Contract source |
|---|---|---|---|
| W (current; ACK 18 Sep decision a) | window 20 + monitor 3 + exit buffer 5 = 28 sessions | 40 | the book's selected contract (median 57 DTE) |
| AM (test) | anticipated-move hold + 3 + 5: 13 sessions for 1_5d, 18 for 6_10d | 19 / 26 | shortest listed expiry at or above the floor and below 40 days, strike closest to the selected strike, two-sided quote inside the 30% friction domain, from the run's `contracts_tested` record |

Both contracts valued with the merged 5+7+8 harness at the horizon hold (5 or 10 sessions), IV solved from mid for both so the comparison is like-for-like (median gap between solved and book IV on the W contract: 6.5 points). The W contract was additionally valued under the Day-10 and Day-20 exit policies the AM contract cannot reach.

## Coverage

305 of 401 actionable rows compared. 92 had no AM contract in the 19–40 day band with a usable quote; 4 had an unsolvable IV. 71% of AM contracts share the selected strike, so the difference is mostly expiry.

## Result

| Median | W (window) | AM (anticipated move) | Difference |
|---|---|---|---|
| DTE | 57 | 22 | −35 days |
| Entry ask | — | — | AM premium 39% cheaper |
| Spread, fraction of mid | 8.1% | 18.2% | AM more than double |
| Solved IV | 53.5% | 45.8% | AM 8 points lower (term structure upward-sloping on 257 of 305 rows) |
| FLAT payoff (nothing happens by the hold) | −17.6% | −34.3% | AM loses twice as much to theta |
| REACHABLE payoff (1.5σ by the hold) | +61.7% | +108.7% | AM pays more if the move comes on time |
| INVALIDATION payoff | −60.1% | −84.1% | AM loses 19 points more when wrong |
| Grid EV at the horizon hold | −9.8% | −14.7% | AM worse by 4.0 points |
| P(positive net exit) | 30.1% | 30.1% | no change |

| Count over 305 rows | Value |
|---|---|
| AM better than W at the horizon hold | 97 (32%) |
| AM positive | 37 · W positive: 24 · W best exit policy positive: 48 |
| AM better than W's best exit policy (Day 5 / 10 / 20) | 76 (25%) |
| AM spread above the pipeline's own 15% friction cap | 203 (67%) · W: 52 (17%) |
| AM spread no wider than W | 22 (7%) |
| Distribution of AM − W grid EV, deciles | −13, −10, −8, −6, −4, −2, 0, +3, +7 points |

By bucket: 1_5d (236 rows) AM −14.6% vs W −10.0%; 6_10d (69 rows) AM −15.9% vs W −9.2%. Same direction in both.

## Where the shorter contract wins

The 97 rows where AM beats W are the rows where it is cheap **and** liquid: median AM spread 11.5% versus 22% where it loses, premium saving 47% versus 35%, and a much higher IV level (W solved IV 68% versus 50%), meaning expensive front-month vol that the move can overcome. Only 65 of the 97 wins have an AM spread inside the 15% cap.

## Reading

1. **On the book as it stands, choosing DTE from the anticipated move costs about 4 points of expectancy per row at the median and is worse on roughly seven rows in ten.** The premium saving is real (39%), but it is paid back through twice the theta loss if the move is late, a 19-point deeper loss at invalidation, and a spread that more than doubles because the shorter expiries are thinner. The decision to pin the runway to the window is supported by the numbers.
2. **The shorter contract is not a horizon decision, it is an expression.** The 97 rows where it wins are identifiable in advance from liquidity and IV, not from the horizon bucket. Under spec §10 that is exactly what expression generation is for: list the short-dated contract as a candidate expression with its own `last_exit_session`, value it beside the long-dated one, and let RAEV pick. That gives the 97 wins without giving the 208 losses, and without any DTE rule.
3. **The test is still bounded by the vol forecast.** AM contracts win where the REACHABLE payoff is largest, and REACHABLE scales with the unvalidated vol budget (see the bias sweep in the impact summary). If ALG-10 finds the forecast biased high, the AM advantage shrinks first.
4. **The spread effect is a pipeline fact.** Two-thirds of the anticipated-move contracts fail the pipeline's own 15% spread cap. An AM rule would push contract selection into contracts the execution model already refuses.

## What this does not measure

- Timing risk. If the move resolves after the AM contract's last exit session, that contract is a total loss while the W contract is still alive. Without the first-passage curve (fix item F1) that cost is not priced here; it can only make AM look worse.
- Realised outcomes. All numbers are scenario values, not returns.

## Recommendation for ACK

Keep decision (a). Do not introduce an anticipated-move DTE rule. Instead add the short-dated contract to the bounded expression set so valuation can choose it where it is cheap and liquid, which the data says is about one actionable row in three.
