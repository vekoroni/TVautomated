# AVSHUNTER governed release — Interpreter outcome truth (2026-09-23)

## Scope

The advisory Pipeline Interpreter now replaces its pre-dispatch `UNKNOWN` marker with an atomic, sanitized terminal receipt when a provider rejection or report-validation failure is known. Transport loss and other unprovable post-dispatch outcomes remain `UNKNOWN`. Every non-complete receipt remains non-retryable on refresh. The Lab labels such rows as requiring review, not as reports still progressing.

OpenAI HTTP rejections persist a bounded status and a validated request ID when supplied. Provider error bodies, API credentials, arbitrary exception text, and report prompts are not written into failure receipts. The Interpreter remains advisory only; no execution, broker, capital, thesis, or Worker 3 authority changes are included.

## Verification

The new offline regressions were red before the implementation. The governed Interpreter/Lab/authority pack passed **60/60** tests after the change; Python AST, JavaScript syntax, and diff whitespace checks passed. Tests use fake transports and made no paid provider calls. C0 production preflight must pass with the release tag at HEAD before this is treated as governed production code. A live provider report is a separate operator-approved acceptance step.

## Existing uncertain attempt

The pre-release KDP marker for run `20260922_223221` remains untouched and unreconciled. It contains no provider response ID or terminal error, so this release does not fabricate a report or authorize a paid retry. The original attempt must be reviewed separately; any new paid attempt requires explicit operator approval and acknowledgement that duplicate provider cost is possible.
