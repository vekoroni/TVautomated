# AVSHUNTER governed release — Interpreter outcome truth (2026-09-23)

## Scope

The advisory Pipeline Interpreter now replaces its pre-dispatch `UNKNOWN` marker with an atomic, sanitized terminal receipt when a provider rejection or report-validation failure is known. Transport loss and other unprovable post-dispatch outcomes remain `UNKNOWN`. Every non-complete receipt remains non-retryable on refresh. The Lab labels such rows as requiring review, not as reports still progressing.

OpenAI HTTP rejections persist a bounded status and a validated request ID when supplied. Provider error bodies, API credentials, arbitrary exception text, and report prompts are not written into failure receipts. The Interpreter remains advisory only; no execution, broker, capital, thesis, or Worker 3 authority changes are included.

## Verification

The new offline regressions were red before the implementation. The governed Interpreter/Lab/authority pack passed **60/60** tests after the change; Python AST, JavaScript syntax, and diff whitespace checks passed. Tests use fake transports and made no paid provider calls. C0 production preflight must pass with the release tag at HEAD before this is treated as governed production code. A live provider report is a separate operator-approved acceptance step.

## Existing uncertain attempt

The pre-release KDP marker for run `20260922_223221` remains untouched and unreconciled. It contains no provider response ID or terminal error, so this release does not fabricate a report or authorize a paid retry. The original attempt must be reviewed separately; any new paid attempt requires explicit operator approval and acknowledgement that duplicate provider cost is possible.

## Addendum 2026-09-24 — Anthropic transport must be workspace-scoped (root cause approved by ACK)

**Observed.** On run `20260924_085940` the first Desk reports sent over the new Anthropic transport (COP, DVN at 18:34 BST; COP retried by the operator at 19:13 after the receipt began persisting the provider's own reason) were rejected with HTTP 400. The persisted detail read: the API key is not scoped to a workspace, so the request must carry the `anthropic-workspace-id` header. The 18:34 receipts carried no detail because the Lab process predated the detail-persisting change and the server never reloads code; they were replayed unchanged on refresh, by the finality rule above, until the operator retired the stored receipt.

**Root cause.** `pipeline_interpreter/anthropic_desk_provider.py` built its client with the key alone. The repository already owns the workspace rule (`anthropic_runtime_config.workspace_id()`, pinned 7 Sep 2026, persisted in `config/anthropic_runtime.json`, used by the macro builder); the Desk provider did not reuse it.

**Change.** The provider resolves the workspace through that single owner at construction, is not ready without it (no paid request is sent; the Lab shows the provider as not configured), and sends every request with the `anthropic-workspace-id` header. No change to schemas, the finality rule or the receipt format. Tests: `tests/test_anthropic_desk_provider.py` (red before the change: header from configuration, missing workspace blocks before the network, workspace id never appears in a rejection); Desk, contract, OpenAI transport and workspace-owner packs re-run green (61 tests). Live acceptance is the operator's next COP report after the Lab is restarted on this code and the 19:13 receipt is retired.

**Out of scope, noted.** `pipeline_interpreter/pipeline_interpreter_engine.py`, `ma_cockpit/ma_cockpit_engine.py` and `news_terminal/news_terminal_engine.py` also construct Anthropic clients without the workspace header and will fail the same way with an organisation key.

## Addendum 2026-09-24 (2) — Controlled failures name their case in typed fields (approved by ACK)

**Observed.** After the workspace fix, the operator's COP request at 19:24 BST reached the model and came back as `PROVIDER_CONTROLLED_FAILURE` at `PROVIDER_RESPONSE`: the transport could not extract a single structured tool call from the reply. The receipt carried only the fixed sentence, the route logs nothing, and the transport discarded the reply's stop reason, so the case (paused server-tool turn, exhausted output budget, prose-only answer, duplicate tool calls, SDK error) could not be told apart. Missing was being reported as neutral.

**Change.** `desk_provider_common.ProviderReplyUnusable` (a `ProviderUnavailable`) carries a reason code from a fixed set (`NO_STRUCTURED_TOOL_CALL`, `MULTIPLE_STRUCTURED_TOOL_CALLS`, `SDK_ERROR`, else `UNCLASSIFIED`), the API's stop-reason token (bounded, else `UNRECOGNISED`) and the ordered content block types (bounded, at most 32). The Anthropic transport raises it in place of the untyped errors. The receipt writer persists `provider_failure_reason`, `provider_stop_reason` and `provider_block_types` on controlled failures. The failure code, the fixed sentence and the finality rule are unchanged; no provider prose, evidence or credential is written. Tests red before the change: four in `tests/test_anthropic_desk_provider.py`, one in `tests/test_interactive_desk_end_to_end.py`; Interpreter-facing packs re-run green (68 tests). The fix for the reply itself waits for the first receipt that names the case.

**19:31 BST attempt, same day.** The operator restarted the Lab from `intelligence-lab\venv\Scripts\python.exe`, a second virtual environment inside the Lab folder that does not have the `anthropic` package (the repository's `venv` and `C:\Python314` do). The transport's `import anthropic` failed after the readiness check, was reported as an untyped controlled failure, and no request was sent. The pre-dispatch stops are therefore typed as well: `SDK_MISSING`, `COST_CEILING_EXCEEDED`, `EVIDENCE_REFS_INVALID` (three further red-then-green tests in `tests/test_anthropic_desk_provider.py`). The Lab must be started with the repository's `venv`.

## Addendum 2026-09-24 (3) — One attempt, configured timeout, measured unknown outcome (approved by ACK)

**Observed.** On the repository `venv` the COP request went out at 19:37:59 BST and came back `PROVIDER_OUTCOME_UNKNOWN` at 19:44:04, 365 seconds later: three back-to-back attempts at the transport's 120-second literal timeout. The Anthropic SDK re-sends a timed-out request twice by default and the transport had not disabled that, so one click was up to three paid attempts, against the no-automatic-retry rule; and 120 seconds is too short for this model with web search and an 8,000-token report.

**Change.** The transport constructs its client with `max_retries=0` (one click, one attempt). The timeout is configuration, `AVSHUNTER_INTERPRETER_ANTHROPIC_TIMEOUT_SECONDS`, defaulting to `DEFAULT_TIMEOUT_SECONDS = 600` (the SDK's own single-request ceiling); unset, non-numeric or non-positive values fall back to the default. Unknown outcomes carry `provider_elapsed_ms`, measured by the route, so a timeout is read from the receipt. Tests red before the change: two in `tests/test_anthropic_desk_provider.py`, the extended timeout test in `tests/test_interactive_desk_end_to_end.py`. Operator note: the three abandoned attempts may have completed server-side and been billed; check provider usage before further retries.
