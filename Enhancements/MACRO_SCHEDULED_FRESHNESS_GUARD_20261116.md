# Scheduled FULL macro freshness prerequisite

The scheduled runner already refreshed the market snapshot before FULL analysis. The stale manual refresh on 16 November bypassed that stage; furthermore, the runner previously continued to paid analysis/board even after a failed refresh. This change enforces the prerequisite without changing model/trading logic or claiming that new transport timestamps make old quotes current.

## Sequence and failure behaviour

PreOpen/PostClose producers and FRED merge -> all-market snapshot refresh -> read-only current-run freshness gate -> FULL analysis -> rotation -> ETF board.

The gate requires the refresh completion to fall between this run's refresh start and the actual check, at most ten minutes old, with matching snapshot clocks, complete refreshed-group declarations, no collection errors and hash-verified parent lineage. It reuses the existing per-source health assessment (60-minute live-bar policy and existing regional completed-session handling). All seven groups must be AVAILABLE; missing, stale, invalid or future source observations stop FULL publication. Valid closed regional sessions retain their original timestamps. If a venue/source cannot provide acceptable evidence, the run stops rather than spending on knowingly stale analysis; no closed-market exception or timestamp upgrade is guessed.

A failed/missing refresh, failed gate or failed FULL packet stops dependent analysis/board stages. Exit 2 on a successfully published packet remains allowed for explicit non-market limitations such as USMI_PARTIAL_EVIDENCE. USMI is not promoted or included in the market freshness gate: incomplete history, unverified evidence, null scores and disabled execution remain explicit.

DATA_ONLY retains its separate path; transfer-only pickup runs no refresh, gate or model jobs. FULL remains configured. Both installed Windows tasks point to this runner and are Ready; task schedules/actions were only read. The protected PostClose `$waitsPastGuard` expression and 16:30 ET target are unchanged. No paid/model/provider calls or evening pipeline are used to test this change.

## Verification

Saved fixtures exercise healthy source timestamps, closed Asia session handling, old/current-run/future/expired captures, collector errors, incomplete groups, parent-hash mismatch, stale/missing/future observations and naive clocks. AST-only PowerShell tests execute the actual publish-control function with fake steps, proving downstream steps cannot run after refresh/gate/packet failures. Separate AST tests evaluate the actual FULL and DATA_ONLY step definitions without executing any producer. Real `-PlanOnly` tests cover PreOpen and PostClose order and timing.

Final regression: **92 passed in 138.20 seconds** across the new gate/control-flow/plan tests plus delivery-lock handling, runner plans, transfer-only delivery, FULL no-write publication guards, preview checkpoints, feed intake, pickup windows and USMI compatibility. No tests skipped or failed. The preceding focused gate/wiring run also passed (22 tests before the two final session-plan cases were added).

Protection checks: publication config SHA256 remains `AA30886A7008117A79BAF2356544A95921A539F4E33A280719B6CCA454BB3609` (FULL). PreOpen remains 08:35 ET; PostClose remains 16:30 ET with the original clock-change guard. Installed tasks remain Ready and still reference the same runner with `-Session PreOpen` / `-Session PostClose`. The live macro packet remains last written 09:21:58 UK and board HTML 09:23:00 UK from the earlier authorized refresh: tests did not rebuild them. This change is active in the local scheduled runner; no commit/push was requested or performed.

For manual FULL work, use the scheduled runner's guarded `-Now -Yes -Session PreOpen` or `PostClose` path as appropriate. Calling `build_macro_json.py` directly remains a low-level API that bypasses this runner prerequisite; the direct builder has not been given hidden provider side effects. Do not reuse a bare builder command as an automated retry after a failure. No automatic retry loop was added.

## Isolated release

ACK subsequently approved committing and pushing only this change. Release branch `fix/scheduled-macro-freshness-20261116` is based on the previously pushed macro recovery release `6666d25`, not the development branch containing other work. The seven-file patch includes the minimum `scripts/refresh_futures_snapshot.py` runtime because that already-used local prerequisite was absent from the published base. Only its refresh step is added to the base runner along with the new guard/control flow; unrelated GEX, intraday-label and wait-variable changes are not copied. No collector, trading, Lane B, data, receipts or backup changes are included.

Clean release-worktree regression: **94 passed in 142.35 seconds**, with no skips or failures. This includes the original 92-test coverage and two injected-bar compatibility tests exercising the packaged refresher, existing collector and gate without network access. The actual PreOpen/PostClose dry plans ran using the existing Python environment through an ignored worktree-local venv junction; no runtime environment was copied or modified. An initial run before that link was available passed 88 with six environment-dependent skips; the final complete rerun replaces that as release evidence.

The release has no diff to the FULL config or PostClose timing block. The active checkout remains on its original branch and is neither staged nor committed by this release workflow. No paid build or evening pipeline was launched.
