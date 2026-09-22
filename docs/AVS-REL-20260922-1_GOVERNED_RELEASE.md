# AVSHUNTER governed code release — 2026-09-22, candidate 1

## Scope

This release governs the current macro input and run-scoped GEX alignment, completed-session options/outcome evidence, EOD thesis handoff, scanner evidence disclosure, read-only Tastytrade observations, and the Intelligence Lab / interactive Pipeline Interpreter integration. The corresponding domain contracts, tests, research designs, and canary evidence are included in Git.

The Lab's run-read paths now consume the frozen final manifest without republishing it. A missing manifest may be built in memory for display only. Quote freshness is visible as execution context; it does not invalidate the ticker thesis. Execution viability still requires a provider quote timestamp.

## Release boundary

- This is a versioned code release, **not** evidence that today's Evening/Morning cycle or a live GPT report has passed acceptance.
- The interactive Interpreter is advisory. Human review and the existing deterministic execution authority remain separate. No broker order or capital-allocation authority is added.
- Routine option-outcome capture and model activation remain off. The isolated canary evidence is recorded in `docs/AVS-MON-004_*`; it is not a production-scale trading outcome claim.
- The Lab can still expose historical run limitations, including rows without authoritative invalidation, as review-only. This release does not waive those limitations.
- Generated runs, database files, API secrets, and operator-local Claude settings are not included in the release.

## Verification contract

Before tagging, require the governed focused and broad regression packs, staged whitespace and credential checks, and Python syntax validation to pass. After tagging, require C0 production preflight to report `NO_UNTRACKED_IMPORTS`, `CLEAN_TREE`, `RELEASE_TAG_AT_HEAD`, and `PRODUCTION_INTERPRETER` as PASS. Do not start a pipeline cycle merely to issue this release. The next normal completed-session Evening run and live Interpreter one-ticker canary are separate operational acceptance steps.

Offline evidence on 22 September: changed-file pack 206 passed plus 7 subtests; broad pipeline pack 558 passed plus 3 subtests; supplemental macro/authority pack 145 passed. All staged Python files passed AST parsing. These packs overlap and must not be summed into a unique test count.

## Operator handoff

Use the `rel-20260922-1` tag to identify this code state. Run the next completed-session workflow through the governed launcher, and assess its terminal manifest and handoff before claiming trading-session acceptance. Do not infer executable trades from advisory macro, Worker 3, historical quoted returns, or a Lab display alone.
