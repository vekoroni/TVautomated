# AVSHUNTER DDD production integration — offline acceptance

Release: `AVS-DDD-PRODUCTION-INTEGRATION-20260905`

Status: **OFFLINE ACCEPTED — CONTROLLED LIVE EVENING→MORNING CYCLE REQUIRED**

## Implemented integration

- Normal `--evening` and `--morning` entry points now resolve through the governed dynamic dispatcher.
- A checked-in runtime profile enables the controlled DDD capability set; AUTO remains disabled.
- Completed profiles, thesis construction, validation, profile lifecycle, Lab resolution, Interpreter resolution and the append-only Decision/Outcome Ledger share the same governed feature contract.
- The Lab and trade-journal ledger writers use that contract instead of independent raw environment reads.
- A new Morning adapter serialises the already-computed Morning Gate result into immutable validation events. It does not fetch data, change direction, select a contract or grant capital.
- BUILD_THESIS does not parse an unrelated prior mixed-session book. VALIDATE and FINALISE retain strict accepted-thesis session checks.

## Verification

- Syntax compilation: PASS.
- Plan-only `python intelligent_orchestrator.py --evening --plan-only --as-of-utc 2026-09-05T12:00:00Z`: PASS; resolved `BUILD_THESIS`; no writes or provider calls.
- Initial focused integration: 161 passed.
- Morning validation/handoff focus after the production-boundary fix: 52 passed plus 3 subtests.
- Read-only replay over the latest stored Morning output: 191 rows produced 191 unique validation-event identities with zero conversion failures (87 CALL, 89 PUT and 15 non-directional).
- Consolidated regression: 1063 passed, 1 skipped, 43 subtests passed, 0 failed.

The repository Python virtual environment points to a removed Microsoft Store interpreter. Tests were therefore executed with `C:\Python314\python.exe` and an isolated pytest dependency directory under `audit/`; production dependencies and runtime configuration were not modified.

## Acceptance still required

1. Operator runs `python intelligent_orchestrator.py --evening`.
2. Verify EOD thesis/profile/lifecycle publication and that the Lab presents the prepared book.
3. During the next observable market session, operator runs `python intelligent_orchestrator.py --morning`.
4. Verify exact validation-event coverage for actionable rows, Execution Gate→Lab parity, Interpreter bundle reconciliation and Decision/Outcome Ledger counts.

Until both live stages pass, the release is controlled-live-cycle ready, not fully production accepted.
