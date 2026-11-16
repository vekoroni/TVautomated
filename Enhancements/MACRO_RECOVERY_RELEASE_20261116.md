# Isolated macro recovery release

Branch: `fix/macro-feed-recovery-fred-20261116`.
Base: `4601ce5`, the already-pushed `macro-delivery-publication-guards-20261110` release. No later Lane B, ETF, trading, retention or other local commits are included. The active development checkout is not switched, staged or committed.

Scope: USMI partial-quality compatibility without authority promotion; explicitly allowlisted producer migrations; London daily transfer-only pickup policy/helper; focused regression tests; recovery/runbook documentation. No source exports, live data, archives, transport receipts or local automation state are committed.

The existing untracked `test_macro_refresh_reliability.py` contains unrelated refresh/board tests. Only its corrected FRED test and four new parameterized safeguards are extracted into `tests/test_macro_fred_freshness.py` in this release. The original working file and all its other tests remain untouched by release packaging.

Clean-worktree verification: **76 passed in 28.18 seconds**, using the existing local Python environment, no provider calls or production publisher. Modules: USMI compatibility, producer aliases, pickup window, FRED freshness, feed delivery, preview checkpoint, deferred writer, FULL publication guard and seed recovery.

`publication_mode` remains FULL (config SHA256 `AA30886A7008117A79BAF2356544A95921A539F4E33A280719B6CCA454BB3609`). `Run-MacroInputs.ps1` is not changed in this branch; its existing `$waitsPastGuard` protection is retained. The active checkout's runner SHA256 remains `6E5BC1170B340F69DEB7231CA97368FA7FC9E42E8F89B8A8D87906FE450ADB58`; the older release-base runner has its own unchanged hash. No runner version is copied between worktrees.

The app automation schedule/prompt was separately updated through the supported app action during recovery. It is not Git state. Pickup transfers existing producer exports only and stops under FULL; paid builds and pipeline runs remain prohibited for this task. Future board consumption requires a separately authorized successful FULL build; the earlier Anthropic insufficient-credit failure remains a funding intervention, not a delivery retry instruction.
