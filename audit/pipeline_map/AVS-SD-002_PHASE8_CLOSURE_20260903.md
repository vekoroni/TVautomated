# AVS-SD-002 Rev 1.1 — Phase 8 implementation and acceptance report

## Outcome

Phase 8 acceptance controls are implemented and tested. The dynamic-session enhancement is **not promoted** and all eight production feature flags remain disabled.

Current release status: **NOT_READY — OFFLINE ACCEPTANCE CLEAN; LIVE ACCEPTANCE PENDING**.

This is not a failure of the new Phase 8 code. It is the release guard correctly refusing activation while the complete regression gate, live-cycle gate and runtime-budget gate remain open.

## Built

- `orchestrator/dynamic_release.py`
  - exact section 19 gate vocabulary;
  - separate live evidence for completed, premarket, RTH and after-hours transitions;
  - required, repository-contained, SHA-256-bound evidence for every PASS;
  - duplicate, missing, changed and out-of-repository evidence rejection;
  - `NOT_READY`, `READY_FOR_LIVE_CYCLE` and `READY_FOR_CONTROLLED_PROMOTION` states;
  - staged `PLAN_ONLY`, `EXPLICIT_COMMANDS`, `DYNAMIC_VIEWS` and `AUTO` settings;
  - refusal to emit any promotion settings before full acceptance.
- `scripts/validate_dynamic_session_release.py`
  - deterministic evidence assessment;
  - atomic assessment output;
  - non-zero exit until fully promotable.
- `tests/test_dynamic_session_phase8.py`
  - fixed closed/premarket/RTH/after-hours/weekend cutoffs;
  - weekend no-phantom-session assertion;
  - provider-confirmed finalisation;
  - exact and partial cache accounting;
  - replay isolation;
  - evidence hash and atomic-write checks;
  - staged-promotion and premature-promotion tests;
  - restore-verifier exit-code regression.
- `scripts/release_baseline.py`
  - fixed successful `--verify-only` result being followed by a false `KeyError` failure.

## Verification

- Phase 8 focused: 13/13 initially, then 22/22 Phase 0 + Phase 8 after restore-tool repair.
- Integrated Phase 0–8 plus authority/handoff: **165 passed, 3 subtests passed, 0 failed**.
- Initial complete top-level production regression: **872 passed, 1 skipped, 43 subtests passed, 25 failed**.
- Reconciled affected-file reproduction: **76 passed, 0 failed**.
- Final current-state production acceptance matrix: **900 passed, 1 skipped, 43 subtests passed, 0 failed** — 877 top-level plus 23 active QA/RCA tests.
- Recursive MSI characterization diagnostic: **1,113 passed, 3 skipped, 33 failed**; retained separately because its failures intentionally assert old/missing functionality and are not production acceptance criteria.
- Restore drill: **PASS** for canonical control plane, historical prices and trade journal; hashes and table counts match and integrity checks are `ok`.

## Reconciled regression groups

The initial 25 failures were preserved as historical release evidence and reconciled against the approved authority and presentation contracts:

1. four monetisability tests and one OLM compatibility test still expect monetisability to hold capital authority;
2. three Lab cache/journal fixtures do not satisfy the current governed publication contract;
3. nine Lab strangle fixtures expect an older non-directional presentation path;
4. two Morning contract-repair tests disagree with current EV/economics comparability semantics;
5. one canonical resolver fixture supplies Sunday 30 August 2026 as a completed XNYS session;
6. five options-research tests expect legacy R:R/liquidity/trigger hard blocks despite the approved advisory policy.

The fixes updated obsolete assertions and incomplete fixtures to exercise the governed contracts. No production authority was weakened. The affected pack and complete production suite now pass.

## Release gate state

- PASS: G02–G17 and G20.
- NOT RUN: G01 final P0 closure, G18A–G18D live transitions, G19 live cost/runtime/disk budget.
- P0-01 through P0-07 are closed offline; P0-08 is the live-cycle requirement and remains open.

## Production impact

None. The legacy `--evening` and `--morning` paths remain unchanged. Dynamic planning, thesis building, validation, profile lifecycle, Lab view, Interpreter resolver, decision ledger and AUTO remain disabled by default.

## Next sequence

1. Execute and preserve one controlled completed → premarket → RTH → after-hours cycle.
2. Measure cold/warm requests, runtime and disk growth to close G19.
3. Close P0-08 and then G01 using the accepted live evidence.
4. Reassess the hash-bound evidence register.
5. Promote in the design order only if status becomes `READY_FOR_CONTROLLED_PROMOTION`.
