# AVSHUNTER solution tournament — Round 2 protocol

**Frozen before execution:** 19 September 2026  
**Authority:** `EXPLORATORY_NO_AUTHORITY`  
**Purpose:** Find testable contract-selection alternatives without changing production.

## Question

Given a frozen ticker thesis and direction, could another contract already present in the same point-in-time option chain have expressed the opportunity more effectively than the contract recorded by the historical pipeline?

This round does **not** change ticker direction, invalidate a thesis, allocate capital, or infer midpoint fills. It separates contract-family discovery from executable quote economics.

## Point-in-time controls

- Candidate rows: `Enhancements/backtest/signal_ticket_backtest_rows.csv`.
- Entry chain: exact candidate session in the read-only Phantom `chain_snapshots` table.
- Exit chain: exact future XNYS session at 1, 3, and 5 sessions.
- No later chain may participate in entry selection.
- A contract without a positive two-sided entry quote is ineligible for an executable alternative. The ticker thesis remains in the denominator and is reported as `NO_EXECUTABLE_FAMILY_MEMBER` when appropriate.
- Outcome marks are reported both ask-to-bid and mid-to-mid. Midpoint results are diagnostic and never treated as executable fills.

## Common family

All alternatives require:

- the same ticker and CALL/PUT side as the frozen thesis;
- entry `bid > 0`, `ask >= bid`, and a positive midpoint;
- DTE covering the planned hold: `dte >= max(7, ceil(hold × 7/5) + 2)`;
- `dte <= 120`;
- absolute moneyness no greater than 20%;
- delta, when present, between 0.15 and 0.85 in absolute value.

Open interest and volume are ranking evidence only. They never delete a family member.

## Pre-registered alternatives

| ID | Selection rule | Business hypothesis |
|---|---|---|
| F0 | Historical recorded contract | Baseline only |
| F1 | Minimum spread; ties by delta nearest 0.45, moneyness, then DTE | Quote friction is the dominant avoidable loss |
| F2 | Moneyness ≤2.5%, spread ≤15%; nearest money, then spread | Near-money geometry improves delta capture without buying extreme spread |
| F3 | Delta 0.35–0.55, spread ≤15%; minimum spread, then delta nearest 0.45 | A narrow delta band is a more stable liquid core |
| F4 | Spread ≤15% and valid IV; maximise a fixed percentile composite: 40% forecast-vol/IV, 30% inverse spread, 20% inverse moneyness, 10% log(1+volume+OI) | Cheap volatility plus execution quality improves expression |
| F5 | Hold ≤5 sessions; DTE 7–21; moneyness ≤2%; spread ≤10%; IV/forecast ≤1; nearest money then spread | The pre-registered convex satellite preserves fast right-tail moves |

F4 percentile ranks are calculated only inside the ticker's contemporaneous eligible family. Forecast volatility is inherited from the frozen ticker row; contract IV is point-in-time chain evidence.

## Measures

For each alternative and horizon:

- eligible and selected coverage;
- no-quote and no-family counts;
- mean, median, hit rate, and session-block 90% confidence interval;
- +50%, +100%, +200%, and +500% frequencies;
- ask-to-bid and mid-to-mid returns;
- ex-post family upper bound, labelled `ORACLE_NOT_TRADABLE`;
- opportunity recall: share of families with an ex-post +100%/+200%/+500% contract for which the rule selected a contract reaching the same threshold;
- selected contract identity stability versus F0.

## Interpretation gates

1. Nine sessions cannot promote a production rule.
2. The two certified normal completed sessions are sensitivity evidence only.
3. Oracle results measure available opportunity, not achievable performance.
4. A rule must improve executable ask-to-bid results without destroying right-tail recall before it may advance.
5. Any apparent winner must be repeated on a larger certified point-in-time history and held-out sessions.

