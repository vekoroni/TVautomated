# Worker 3 current-state canary audit — 2026-09-07

**Recommendation: NO-GO for paid activation at the current state.** The authorized free token-count preflight returned HTTP 400. The fail-closed boundary prevented a paid Messages generation. Live end-to-end acceptance is therefore not established. Do not rerun the live command under the existing authorization.

## Scope and result

The existing dirty repository was reviewed in place. Only Worker 3 activation, its preparation CLI, the new canary harness, its first-party tests, and this dedicated audit directory were changed. The checked-in provider release remains INSTALLED_DISABLED. No capital permission, governed direction, selected contract, production signal, pipeline output, or production database was changed.

The initial fake-only scope was updated to authorize one free count_tokens request followed by at most one paid claude-sonnet-4-6 Messages generation, with a 500,000 microusd ($0.50) ceiling and no retries.

| Measurement | Result |
|---|---|
| Governed run | 20260906_213931 |
| Invocation | inv_3f44dcdb0f5d69ba30ec4f88 |
| Trading session | 2026-09-04 |
| Governed action | BUILD_THESIS |
| Candidates / prepared / exceptions | 264 / 256 / 8 |
| Prepared CALL / PUT | 170 / 86 |
| Original suite | 279 passed, zero failures/errors/skips |
| Integration suite including new regressions | 40 passed, zero failures/errors/skips |
| Offline scenarios | Five, all expected outcomes observed |
| Live token-count requests | 1, HTTP 400 |
| Paid Messages generations | 0 |
| Retries | 0 |
| Paid generation cost | $0; no generation sent |
| Counted worst-case cost | Unavailable; preflight rejected |
| Live job at stop | PREPARED |
| Live structural/semantic/projection acceptance | Not reached |

## Exact code changes

- `worker3/integration/activation.py`: count every post-dispatch attempt before invoking the adapter, including malformed envelopes and transport failures; allow a durable REVIEW_REQUIRED report to replay even after the one-call process cap is exhausted.
- `worker3/integration/runner.py`: add repeatable `--ticker` selection and pass its exact immutable worklist to preparation. Existing no-ticker behavior is retained.
- `worker3/integration/current_canary.py`: add latest-completed governed resolution, full current-state intake, deterministic directional selection, disposable SQLite stores, a fake transport, controlled failure exercises, real interpreter restart/replay, exact Flask route tests, release/budget checks, and explicit one-generation live mode with a persistent attempt latch.
- `tests/test_worker3_current_canary.py`: nine first-party tests covering the harness, governance resolution, exact selection, CLI ticker routing, both runtime regressions, and frozen-request token-count/cost/no-retry controls. Existing tests were not weakened.

## Confirmed defects and bounded fixes

1. **Malformed provider envelope did not consume the runtime call allowance.** `adapter.generate` could raise before the counter increment. A second queued job could then dispatch within the same runtime despite a one-call limit. The counter now increments before adapter/provider code. The rejected attempt remains UNCERTAIN and retains its cost reservation.
2. **Durable replay was blocked by an exhausted call allowance.** The process cap was checked before the REVIEW_REQUIRED branch. A successful one-call job whose report projection failed could not recover in the same runtime. Replay now occurs before the paid-dispatch cap; it does not invoke a provider.
3. **Operator selection gap.** The preparation CLI could stage an entire run but had no explicit one-ticker worklist argument. The coordinator already supported this operation; the CLI now exposes it.

`pre_fix_regressions.log` runs the two new runtime regressions against an in-memory reconstruction of the original execute method: two tests, one assertion failure and one replay error. No source file was reverted for that check. Both tests pass on the final implementation.

## Current data exceptions

The following eight candidates were isolated before job activation. Each has `LIVE_OPTION dataset identity is absent or invalid`: BKSY, CAPR, COLL, CRDO, HIMS, PRVA, QDEL, TTD. These are current selected-quote lineage exceptions, not demonstrated Worker 3 code defects. No substitute quote, ticker, direction, or contract was selected.

## Offline evidence

| Candidate | Direction | Scenario | Durable state | Result |
|---|---|---|---|---|
| AAOI | CALL | valid | REVIEW_REQUIRED | Expected outcome passed |
| AA | PUT | valid | REVIEW_REQUIRED | Expected outcome passed |
| AAOI | CALL | envelope | UNCERTAIN | Expected outcome passed |
| AAOI | CALL | authority | UNCERTAIN | Expected outcome passed |
| AAOI | CALL | projection_failure | REVIEW_REQUIRED | Expected outcome passed |

Every scenario made exactly one deterministic fake transport call. Valid fake responses contain empty claims and deliberately produce BLOCKED_DRAFT semantic findings; this tests conservative advisory projection rather than pretending to be a substantive model assessment. Malformed envelopes and invalid authority remain UNCERTAIN, retain unknown-cost reservations, and cannot replay a provider call. Successful and recovered reports carry ADVISORY_ONLY, human_review_required=true and execution_permission=false.

For each completed case, exact JSON and HTML routes returned 200; wrong run, wrong ticker, and wrong assessment returned 404 on both routes (six negative lookups per completed case). Report recovery ran both in the original runtime and a new Python interpreter reopening the SQLite stores, with a transport that fails if called. Every replay reported provider_called=false.

Activation tests rejected missing operator approval, disabled production release, unapproved model, excessive job count, a second activation exceeding the cumulative release ceiling after database reopen, and a release file modified after runtime initialization. The original and integration suites additionally cover durable budgets, leases, structural validation, semantic review and disabled production Lab startup.

## Live attempt and limit

The exact current candidate was **AAOI / CALL**, contract `AAOI260918C00110000`, thesis `AAOI:CALL:2026-09-04:OLM2`. Exactly one ticker/job was prepared in disposable storage. Model: `claude-sonnet-4-6`. Complete frozen request size: 251,127 UTF-8 bytes. Maximum output: 8,192 tokens; timeout: 60 seconds. No evidence was truncated.

The initial 100 KB harness limit was too small for the real approximately 250 KB packets. This harness configuration issue was corrected to 500 KB for complete evidence. A strict byte-per-token input bound would exceed the paid cap, so the clarified authorization allowed the free token-count preflight. The final harness requires a successful count, verifies the exact request hash, prices counted input plus all output tokens, and additionally reserves 4,096 input tokens for counting drift. A changed request or ceiling violation blocks generation.

Anthropic returned HTTP 400 from `/v1/messages/count_tokens`. The error body and headers were not retained. The execution environment contains an API key but no ANTHROPIC_WORKSPACE_ID. Missing workspace selection is the leading evidence-backed explanation: [Anthropic authentication documentation](https://platform.claude.com/docs/en/manage-claude/authentication#select-a-workspace) states that a multi-workspace/identity-linked key without anthropic-workspace-id returns HTTP 400. This is an inference, not a conclusive diagnosis: the key scope and actual error body were not established. The count packet excludes max_tokens, its approximately 251 KB size is far below the [32 MB endpoint limit](https://platform.claude.com/docs/en/api/overview#request-size-limits), and the requested model is active. Required remediation is to configure the correct wrkspc_-prefixed workspace selector, or rotate to a key scoped to one workspace, then obtain approval for a new canary. No actual workspace identifier or credential is included in this report. No paid request followed; no API retry was attempted. The latch `LIVE_ATTEMPT_LATCH.json` remains in place.

Input/output prices used are $3/$15 per million tokens, verified from [Anthropic Sonnet 4.6 documentation](https://platform.claude.com/docs/en/models/sonnet-4-6/overview). Anthropic describes [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) as free and as an estimate that can differ slightly from generation usage; the extra margin is therefore explicit, not a billing guarantee from the provider.

No real assessment, token usage, semantic grounding result, or live Lab report exists from this attempt. The unchanged key was accessed only from the environment for HTTPS headers. The only persisted credential identifiers, where generated, are the permitted sanitized source/fingerprint; no key was printed or persisted.

## Identities and hashes

| Item | SHA-256 / identity |
|---|---|
| Plan | b81106ed1c35d136b03e25db50e60596eb234f75587e5c3e9bc52f6892268e56 |
| Run metadata | f0a14597df23f268e6be8fa38876917268d27c77e8aa9db3a30e792ee69ad885 |
| Final manifest | 8a2e80078fe335dc13cf6b368f2f5f63b9c5a8f92e9e783b3c027b7d202db092 |
| Lab opportunity book | 8000d37c3595903a3b6f21aa05d4eb58fd65df3c19d898d27b86ebda30b35d9d |
| Integration policy | 077e060441df2c39b712d403b2eb23a7231e4a22f6e888840bd0a3c159601da1 |
| Production provider release | 24fc37f526eee6b038aa44500c7a7d9da81f68ff00812b48e9534014e3b91f80 |
| Live job_id | a78bea24f93e5eee2466f0ce2b20388edc2fc1c3584c7bd05d180d4e7485298f |
| Live job_key | 3b2e5afd3907c18c671485f3d151f5e35244429a928690032973c01044a2cc1b |
| Live evidence_hash | edf989e378a87fbf660dba6357ce2e505e2bf09dfee1b9250b90532839f4bebe |
| Live context_hash | 5dced2806750d6bcfecdfa00af1cde88d9d63a787bcd400b1b5cd580666c2fe9 |
| Live request_hash | 24275ca3e8203412d984d4162f6d599780b596e25a03d36d69d2049592041ba9 |
| Live request_fingerprint | 40fb907300d4e3b23e50d4713ac60309daaf6245886020f5d2182ebaeccccf50 |
| Live release_hash | a1cfd29dd9cffae8c2cc233e61e0e280d7c5a1a62c8c211234f369a65bc350e8 |

Every candidate intake ID, evidence hash, job ID and exception is retained in `intake.json` and `offline.json`. Completed offline cases also retain the activation record, sanitized receipt, charge rows, ordered durable events, structural response, semantic findings and full advisory view.

## Preservation and test evidence

`protected_before.json` and `protected_after.json` contain matching hashes for 1,671 files across the selected run, checked-in Worker 3 contracts, canonical SQLite files and existing Worker 3 data stores. No protected hash changed.

The dirty-worktree baseline contains 310 file hashes and was captured after the two initial source edits to activation.py and runner.py. There were 236 observed changes/disappearances in unrelated temporary test-output paths during this task; none outside those temporary paths. Those outputs were neither edited nor restored by this canary. All unrelated source-file baseline hashes remained unchanged. This task made no writes to Discovery, Vanguard, Options Intelligence, Morning Gate, macro or production signal logic.

The 279-test original suite was loaded from `C:/Users/ACKVerissimo/Documents/Codex/2026-07-24/a/worker3_foundation/tests` with an assertion that `worker3` imported from the integrated repository. The final 40-test integration run includes source bridge, coordinator, activation and current-canary modules. Complete verbose logs and machine-readable summaries are retained beside this report.

## Repeatability and next decision

Offline command (safe to repeat):

```powershell
python -B -m worker3.integration.current_canary
```

First-party integration command:

```powershell
python -B -m unittest tests.test_worker3_avshunter_source_bridge tests.test_worker3_coordinator tests.test_worker3_activation tests.test_worker3_current_canary
```

The live attempt is intentionally latched and must not be repeated under the consumed authorization. First resolve the token-count HTTP 400 using existing diagnostics or newly authorized work, then obtain explicit authorization for any new provider request. Keep the production release disabled until a new controlled canary passes HTTP success, exact model, structural v2 validation, semantic review, durable REVIEW_REQUIRED state, exact advisory Lab projection, reconciled usage/cost within the cap, and replay without a second paid call.

This audit validates technical controls on current evidence. Even a future successful single assessment would establish technical end-to-end integrity and that assessment’s evidence grounding only; it would not establish statistical prediction quality, trading accuracy, profitability, or permission to trade.
