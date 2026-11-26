# Isolated Macro Operating Cycle release — 26 November 2026

ACK requested only the operating cycle, end-to-end macro integration, tests and handoff documentation. Branch `feat/macro-operating-cycle-integration-20261126` is based on the published macro foundation `2635b4f1a33d56a3e437bf0626bedf7974bc55bb`.

Only new operating-cycle/publication modules, versioned policy/schema, saved-only tools, shared narrative renderer, narrow board/Lab integration hunks, tests and handoffs are included. Live checkout remains on `laneb/lab-first-handoff` at `82ef06e92f289cc2d6fb3e4153be055cc2bda86f`. No Lane B commits are carried. Older per-ETF/triage/store-writer work and unrelated source-health/presentation edits are not copied wholesale from live board files.

No generated publication, saved response, database, backup, receipt or data-folder change is included. Historical artifact paths in handoffs are evidence references, not committed files. The shared change log resides under `data/`; ACK's explicit instruction to leave data untouched takes precedence, so the commit action is recorded here instead of modifying or staging that file.

Phase 1 MAC-03/07/04/05/08/06/09 code is implemented and saved-data tested. This does not mean every item in the entire brief is operationally complete: real authored probabilities, central-bank calls and ETF world marks remain missing; scheduled-run acceptance is pending because scheduling stays disabled. MAC-10..14 and the rest of MAC-15 remain plan-only. Board/Lab narrative readers are included under the subsequent end-to-end approval. No calibrated forecasting or full outcome coverage is claimed.

| when_utc | agent | branch | commit | change | runtime evidence |
|---|---|---|---|---|---|
| 2026-11-26 | Codex | feat/macro-operating-cycle-integration-20261126 | SELF | Isolated advisory cycle and coordinated board/Lab publication; no providers, paid builds, pipeline, schedule or data changes | Saved runtime in E2E handoff; clean-branch tests recorded before commit |

Pushing this branch does not deploy it over the running checkout. Merge/release reconciliation must preserve unrelated existing ETF/Lab work. FULL, standing budgets and PostClose timing are inherited unchanged. All three MacroInputs tasks remain disabled; no task enablement is part of this release.

## Clean-branch verification

127 Python tests executed: **126 passed; one unchanged baseline Worker 3 static-call assertion failed**. The exact same assertion fails on the untouched published base `2635b4f`: its orchestrator has two occurrences of `materialize_worker3_market_environment(` while that historical test expects one. No orchestrator or Worker 3 changes were introduced to hide/fix this unrelated baseline mismatch. The earlier 127-pass live-checkout result in the handoff is separate historical evidence, not the isolated result.

Both JavaScript harnesses pass. Isolated saved end-to-end replay passes with network blocked: all three feed chains verified, board and Lab HTTP 200, matching narrative identity/hash, original saved payload and all 115 ETF records exactly preserved. Isolated publication `8c5a63f014df08e89c7cc2b9636fbff3eccc80f33559a24c3670f41cdae999b7` differs from the running checkout's publication because unrelated template features are excluded; the narrative ID/hash is identical.

Evidence references (not committed data): `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_ISOLATED_TESTS_20261126` and `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_ISOLATED_REPLAY_20261126`. No live .env/database/runtime bindings were added to this worktree. Its tests use isolated output folders and read explicit saved evidence only.
