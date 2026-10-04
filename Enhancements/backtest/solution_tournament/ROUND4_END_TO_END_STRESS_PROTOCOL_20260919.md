# AVSHUNTER solution tournament — Round 4 integrated monetisation and stress protocol

**Frozen before execution:** 19 September 2026  
**Authority:** `EXPLORATORY_NO_AUTHORITY`  
**Objective:** identify a reliable, testable route from ticker opportunity to executable monetisation without altering production.

## End-to-end path under test

```text
Frozen ticker candidate
  → direction rule
  → same-session CALL/PUT family
  → core / value / convex expression
  → option-versus-shares decision
  → monitor and re-rank when no core contract is executable
  → executable future bid
  → outcome and tail attribution
```

Macro remains advisory and has no veto, direction, rank, or capital authority. Capital allocation is not modelled.

## Frozen evidence

- H candidate rows and their exact run/session/ticker identities.
- Same-session Phantom option chains opened read-only.
- Exact future Phantom chains at 1, 3, and 5 XNYS sessions.
- Canonical underlying closes opened read-only.
- No future quote, price, outcome, or stress result may participate in entry selection.

## Direction alternatives

- `D0_CURRENT`: frozen pipeline CALL/PUT direction.
- `D1_MEAN_REVERSION_5`: PUT after a positive trailing five-session return, otherwise CALL.
- `D2_MOMENTUM_20`: CALL after a non-negative trailing twenty-session return, otherwise PUT.

The two alternatives are retained because they represent structurally different hypotheses. Round 3 did not promote either.

## Contract lanes

All lanes require a positive two-sided quote, hold-covering DTE, DTE ≤120, moneyness ≤20%, and delta 0.15–0.85 when delta exists. OI and volume are ranking evidence only.

- `E0_RECORDED`: historical contract; current direction only.
- `E1_CORE`: delta 0.35–0.55 and spread ≤15%; minimum spread then delta nearest 0.45.
- `E2_VALUE`: spread ≤15%; fixed composite of volatility cheapness, inverse spread, inverse moneyness, and activity.
- `E3_CONVEX`: delta 0.20–0.35, moneyness ≤10%, spread ≤15%, IV/forecast ≤1.0; maximise volatility cheapness then activity. This is a separately disclosed alternative, not a replacement for the core.

## Dynamic expression rule

For each direction rule, rank the E1 core's `contract IV / forecast volatility` within its contemporaneous session. The cheapest 40% use the core option. Otherwise:

- CALL thesis → long shares;
- PUT thesis → no trade because short shares are outside scope.

No-trade rows remain in the opportunity denominator but are excluded from executed-return means. Participation and missed-tail rates are reported explicitly.

## Liquidity maturation

When E1 has no executable member at the original session, search the next two completed sessions using only evidence available on each search date. Select the first date on which E1 becomes executable. It may enter only when that date precedes the tested exit horizon. This recovers an expression; it never changes or invalidates the ticker thesis.

## Outcome rules

- Option entry at observed ask; option exit at observed bid.
- Midpoint returns are diagnostic only.
- Shares enter at the canonical close on the candidate session and exit at the exact future close.
- No underlying stop is applied in this round; previous tests showed it damaged the right tail.
- Horizons are 1, 3, and 5 XNYS sessions.

## Stress matrix

Every integrated scenario is measured under:

1. `BASE_EXECUTABLE` — observed ask-to-bid or share close-to-close.
2. `SPREAD_WIDEN_25` — option half-spreads widened 25% at entry and exit.
3. `SPREAD_WIDEN_50` — option half-spreads widened 50% at entry and exit.
4. `QUOTE_DROPOUT_10` — deterministic 10% of option quotes unavailable; affects participation, never becomes a zero return.
5. `QUOTE_DROPOUT_25` — deterministic 25% quote unavailability.
6. `REMOVE_TOP_1PCT` — removes the top 1% of executed returns to measure tail dependence.
7. `SPY_BULL` / `SPY_BEAR` — entry-session SPY 20-session return state.
8. `SPY_VOL_HIGH` / `SPY_VOL_LOW` — entry-session SPY trailing realised volatility split at the sample median.
9. `LIQUIDITY_MATURATION` — E1 with up to two-session monitoring where the initial family is unavailable.

## Reliability bar

A candidate may advance only if:

- executable mean is positive with a session-block 90% lower bound not materially below zero;
- the result is not created by counting no-trade or missing-quote rows as zero;
- participation and missing-data rates are disclosed;
- the conclusion survives spread widening and removal of the top 1%;
- it is not profitable in only one SPY regime;
- core plus convex presentation improves +100/+200% opportunity recall over core alone;
- the result is directionally consistent across more than one independent horizon and later replicates on additional certified sessions.

Failure is informative: the report must identify whether direction, option price, liquidity, spread, or tail dependence caused rejection.

