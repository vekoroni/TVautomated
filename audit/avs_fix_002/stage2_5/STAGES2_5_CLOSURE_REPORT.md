# AVS-FIX-002 Stages 2–5 closure report

Baseline: `3e660bd2483563e092308df7eaac6cbfbb6268ca`
Scope: numeric truth, deterministic economics, DOI lifecycle integration, macro context, Lab v4 projection and immediate decision/fill capture.

## Delivered

- Stage 2: `vol_budget_v2`, cumulative 5/10/20-session fractions, arbitrary 1–20 session budgets, explicit spread units, silent-default inventory, and append-only `decision_record_v2` / `fill_record_v1` with operator CLI.
- Runtime adapters: Opportunity Tier and Execution Gate consume and publish explicit spread units; Layer 3 publishes canonical cumulative volatility budgets; Trigger EV prefers the canonical 10-session fraction while retaining the declared legacy fallback.
- Stage 3: one macro-derived `MarketRateObservation` per run; `reachability_v1`; 54-cell CALL/PUT scenario grid; XNYS/calendar bridge reuse; half-spread friction; scenario monetisability; payoff-shape convexity; deterministic utility; forecast-validation instrument.
- Stage 4: DOI now runs after Q-Omega evidence is commuted to its Options boundary; ticker exceptions remain retained; existing append-only family/ranking/lifecycle stores remain authoritative only for advisory contract intelligence; `hysteresis_v1` is implemented behind approval.
- Stage 5: USMI routing/scenario and structure evidence are advisory; canonical DOI metadata is projected into `lab_signal_book_v4`; the presentation projector cannot grant execution.

## Verification

- Unit/property/integration/stored-run replay and compatibility pack: **221 passed**, plus a final Lab/orchestration focus of **104 passed** after the v4 CSV contract was completed.
- Stored replays: `20260910_150045`, `20260911_115904`; both resolve governed T3M rate, retain directed 1–20-session populations, and reproduce **100% Q-Omega annual-vol join coverage** (1,242/1,242 and 1,256/1,256 directed tickers respectively).
- Consolidated compatibility pack: **259 passed, 72 subtests passed, 0 failed** after two additive-compatibility corrections. The Stage 0 import-graph guard will remain red only until these new modules are staged in Git; Codex cannot write `.git/index.lock` on this host, so the exact operator staging command is part of handoff.
- No provider calls or full production pipeline execution were made by this build.

## Governed non-activation (not code defects)

1. `profit_floor=0.25` remains `profit_floor_approved=false`; monetisability therefore publishes `INDETERMINATE / PROFIT_FLOOR_NOT_APPROVED` rather than inventing production policy.
2. Hysteresis values remain `approved=false`; the engine and tests exist but the previous selection policy remains active until ACK approval.
3. Forecast bias remains `UNVALIDATED`, multiplier 1.0 and unapplied until time-ordered validation passes.
4. Overlay retirement requires two stored-run and two normal-cycle parity records; the overlays remain installed as oracles.

## Capital-agnostic addendum — 2026-09-12

The earlier `capacity_v1` implementation was superseded by owner decision
`ACK-20260912-CAPITAL-AGNOSTIC`. AVSHUNTER assesses monetisability and current
execution evidence but does not allocate capital. The capacity calculator,
desk-budget configuration and Lab capacity fields were removed. Any future
portfolio allocation is a separate downstream bounded context.

## Acceptance state

`OFFLINE_BUILD_COMPLETE_AWAITING_CONTROLLED_CYCLE`

Morning validation is not required to verify the completed-session arithmetic build. It remains required before claiming full live-cycle production acceptance.
