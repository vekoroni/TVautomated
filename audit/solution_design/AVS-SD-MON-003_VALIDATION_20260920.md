# AVS-SD-MON-003 — As-Is Validation Record

**Date:** 20 September 2026  
**Design:** `docs/AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md`  
**Repository HEAD inspected:** `785290ccb1115b7069edb8cd7fda0608d46e8f2c`  
**Method:** Read-only code, configuration, register, backtest and stored-run review. No pipeline or provider API was executed.

## Verdict

The design is implementable through existing DDD boundaries. It does not require a replacement pipeline or a new market-data database. It correctly places path forecasting downstream of the governed thesis and contract-family generation and upstream of advisory presentation.

The design must start with Phase 0 and Phase 1. A predictive model cannot be built honestly from the current production learning snapshot because planned-hold lineage and option outcome labels are not available to the fit population.

## Current-state checks

| Check | Evidence | Result |
|---|---|---|
| DOI activation | `config/doi_runtime.json`: enabled, `ACTIVE_ADVISORY`, decision authority `NONE`, execution `HUMAN_ONLY` | Compatible |
| Probability-model activation | `config/governed_constants_v1.json`: `model_activation_enabled=false` | Correctly gated |
| Value selection | `value_selection_mode=SHADOW` | Compatible |
| Worker 3 | enabled with Lab projection, advisory contract | Not a design authority |
| Share support | C12 declares `OPTION` and `SHARES` | Partial |
| Ticket issuance | `avshunter/c12_outcome/signals.py::decide` returns `expression=OPTION` only | Shares and combinations outstanding |
| Learning record count | 11,454 complete records | Infrastructure exists |
| Fit-eligible count | 0 | Blocking |
| Planned-hold lineage | all complete records excluded for `PLANNED_HOLD_UNAVAILABLE` | Blocking |
| Option outcomes | 0 available; 11,454 `UNDERLYING_ONLY` | Blocking |
| Model state | `INSUFFICIENT_OUTCOMES`, activation disabled | Correct |
| Latest run | `20260919_205844`: technical PASS, semantic DEGRADED, health 90 | Not final acceptance |
| Latest run tradeability | false; Morning validation required | Expected before Morning |
| Missing invalidation | 162 selected-handoff rows | Genuine semantic defect |
| Worker 3 ticker context | 1,545 stale, 0 available | Advisory data gap |
| Release state | working tree contains extensive modified/deleted/untracked paths; no clean tagged current baseline | Blocking for release evidence |

## Register consistency

The design preserves the frozen controls in the main scenario register and both addenda:

- thesis direction is not changed by S-ACT or CEX evidence;
- missing or unattractive contracts become monitoring states;
- OI and printed volume remain separate;
- next-session OI is excluded from original entry decisions;
- executable ask-to-bid results are primary;
- wider-spread stress is mandatory;
- every trial is recorded;
- historical mechanism discovery cannot authorize production; and
- later completed sessions are required for replication.

The permitted-expression scope is aligned: long shares, long calls, long puts, shares plus a long call, shares plus a long put, or no current expression. Short shares and straddles/strangles are excluded.

## Backtest consistency

The design accepts the tournament's supported findings:

- S-ACT-9 carries relative information but remains negative after friction;
- all tested static CEX selectors remain negative;
- fixed-horizon hindsight selection remains negative;
- joint contract-and-exit hindsight selection provides a positive feasibility ceiling; and
- the next valid research target is a path/competing-risks problem.

The design does not convert the hindsight oracle into an executable policy.

## Required pre-model repairs

1. Commit and govern the activity/PCR correction.
2. Restore planned-hold lineage to outcome records.
3. Capture daily option bid paths for monitored family members.
4. Repair idempotent/superseding option-observation identity.
5. Reconcile all DOI generated/assessed/ranked/exception populations.
6. Correct the remaining missing invalidation lineage.
7. Restore disk headroom and prove final archive completion.
8. Establish a clean tagged release baseline and update the one stale provider-timestamp test.

## Structural fit

Existing modules provide appropriate integration seams:

- `domain/dynamic_options_intelligence.py`;
- `domain/dynamic_options_lifecycle.py`;
- `domain/dynamic_options_probability.py`;
- `domain/dynamic_options_ranking.py`;
- `domain/dynamic_options_outcomes.py`;
- `domain/outcome_learning.py`;
- `canonical_data/dynamic_options_*`;
- `canonical_data/decision_outcome_ledger.py`;
- `canonical_data/outcome_maturation.py`;
- `avshunter/c12_outcome/`; and
- `domain/lab_signal_book_v4.py`.

The build should extend these services and contracts. Creating another pipeline, ledger, Lab schema family or options store would be architectural duplication.

## Validation decision

`AVS-SD-MON-003` is approved as the design baseline for controlled development, subject to Phase 0 baseline governance. It creates no production authority and does not approve any current research model for live selection.
