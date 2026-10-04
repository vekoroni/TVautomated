# AVSHUNTER Backtest Scenario Register Addendum — CEX

**Registered:** 2026-09-20  
**State:** `EXPLORATORY_NO_AUTHORITY`  
**Purpose:** Adaptive contract/execution tournament following the S-ACT activity finding.

## Evidence limitation

The source sessions were already inspected in Round 4 and S-ACT. They are not a virgin holdout. This batch may identify mechanisms and reject alternatives, but cannot promote production behaviour without replication on later completed sessions.

## Frozen invariants

- Preserve the recorded ticker thesis and CALL/PUT direction.
- Never remove a ticker thesis because a contract is temporarily unattractive.
- A missing/non-executable contract becomes `MONITOR_CONTRACT`, not an invalid ticker.
- Use only entry-cutoff evidence to rank contracts.
- Next-session OI cannot rank the original entry.
- Macro, activity and model output remain advisory.
- No capital allocation or production write.

## Scenario family

| ID | Technique | Description |
|---|---|---|
| CEX-0 | Recorded control | Pipeline-recorded contract. |
| CEX-1 | Minimum-spread current | Choose the available current-session option with the smallest quoted spread. |
| CEX-2 | Premium-floor spread | Minimum spread subject to entry ask of at least $0.25, $0.50 or $1.00. The ticker remains monitored when none qualifies. |
| CEX-3 | Deterministic utility | Rank current contracts using spread, IV/forecast alignment, DTE and moneyness without outcome fitting. |
| CEX-4 | Logistic selection | Purged walk-forward probability of achieving at least +25%. |
| CEX-5 | Random-forest selection | Nonlinear benchmark using the same entry-time features and purged training. |
| CEX-6 | Switching hysteresis | Retain recorded contract unless the alternative model probability exceeds it by 0.05 or 0.10. |
| CEX-7 | Liquidity maturation | Permit delayed `E4_MATURED_CORE` expression; record entry delay and never back-date the fill. |
| CEX-8 | Cross-layer combination | Apply the already-purged S-ACT-9 score to 10%, 20% and 30% priority bands, then independently select the CEX-0/1/2/3/4/5/7 contract. All lower bands remain monitoring opportunities. |
| CEX-9 | Feasibility bounds | Test 1%, 2% and 5% priority sensitivity, random-contract controls, hindsight best-contract upper bounds, and a hindsight best contract-plus-exit-horizon bound across days 1/3/5. Oracle results diagnose learnability only and can never become an executable rule. |

### Adaptive registration note

CEX-8 was registered after observing that CEX-0 through CEX-7 improved relative returns but did not monetise the full population. It is therefore an adaptive mechanism-discovery test, not independent confirmation. The S-ACT score is frozen from its earlier purged walk-forward run; it is not refitted against CEX outcomes.

CEX-9 was registered after CEX-8 remained negative. Narrow priority bands are sensitivity diagnostics, not permission to discard other ticker theses. The oracle explicitly uses future outcomes and is only a ceiling: it is excluded from every acceptance decision.

## Execution manipulations

All returns exit at the observed bid unless otherwise stated.

- marketable entry at ask;
- limit entry capturing 25% of the quoted spread, conditional on fill;
- limit entry at mid, conditional on fill;
- 25% and 50% spread-widening stress;
- quote outcome dropout of 10% and 25%;
- current-session-only versus delayed-maturation contract sets.

Conditional limit results are not assumed fillable and cannot independently pass.

## Acceptance gate

A scenario can only become a replication candidate when:

1. ask-to-bid mean return is positive;
2. 50%-wider-spread mean remains positive;
3. session-level improvement has absolute paired t-statistic at least 2 with positive mean delta;
4. the sign is positive in at least two independent test sessions;
5. observed outcome coverage and monitored/no-contract counts are disclosed;
6. no result depends on future OI, mid-price fills, or removing losing tickers after outcomes are known.

Passing this adaptive batch is not production acceptance. Replication on new completed sessions is mandatory.
