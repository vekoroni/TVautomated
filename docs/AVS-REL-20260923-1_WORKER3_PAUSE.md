# AVSHUNTER governed release — Worker 3 pause (2026-09-23)

## Scope

This release pauses the optional Worker 3 advisory provider and its Intelligence Lab surface. The checked-in provider release is `INSTALLED_DISABLED`, with provider execution and Lab projection disabled. The Lab does not mount Worker 3 browser routes or show its launch button and ticker controls. The interactive Pipeline Interpreter remains a separate advisory path and is unchanged.

No Worker 3 history, contracts, or implementation files are deleted. This pause does not alter the governed thesis, deterministic execution authority, broker permissions, capital allocation, or the Evening/Morning data path.

## Verification and acceptance

Before tagging, run the governed Worker 3/Interpreter regression pack, check the staged diff for whitespace and secrets, and parse staged Python files. After tagging, require the C0 production preflight checks `NO_UNTRACKED_IMPORTS`, `CLEAN_TREE`, `RELEASE_TAG_AT_HEAD`, and `PRODUCTION_INTERPRETER` to pass. The live Lab must return a healthy response, report the Interpreter as provider-ready, and not expose the Worker 3 browser route. A green release gate does not itself prove a new Evening/Morning cycle or a live Interpreter report.

The 23 September governed focused pack passed **68/68** tests across Worker 3 activation, browser launch, coordinator, output bounds, validation quarantine, and Interpreter/Lab integration. The staged diff passed whitespace and credential-pattern checks, and all four staged Python files passed AST parsing. The live Lab reported `health=ok`, `interpreter_provider_ready=True`, no Worker 3 Python process, and HTTP 404 for its browser route. No provider call or pipeline cycle was started for this release.

The broader compatibility pack also identified one pre-existing stale timeout-test assertion: the 22 September runtime records `PROVIDER_RESPONSE`, while the test still expected the older `PROVIDER` value. The test assertion was aligned to the actual controlled-failure vocabulary; no timeout-handling production logic was changed.

The complete Worker 3/Interpreter compatibility rerun then passed **160 tests and 8 subtests**, with no failures or skips. This pack overlaps the focused 68-test pack and should not be added to it as a unique-test count.

## Reversal

Reactivation requires a separate reviewed provider release, focused regression and governance checks, and an operator-approved live canary. Do not merely re-enable the Lab button.
