# AVS-MON-004 — Slice 1 build evidence

**Date:** 22 September 2026
**Scope:** point-in-time/exact-contract label capture bridge only.
**Production state:** wired but opt-in; `AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED` defaults off. No live database labels were written during this build.

## Test-first sequence

1. Added canonical-reader and mature-family tests to `tests/test_dynamic_options_outcomes.py` before the adapter existed. The initial run failed with `ModuleNotFoundError: canonical_data.option_outcome_maturation`.
2. Added `canonical_data/option_outcome_maturation.py`. An initial test exposed a wrong price adjustment convention and an omitted governed ticker argument. Corrected both before proceeding.
3. A further red test exposed a real UTC-date defect: an EOD assessment published after midnight UTC could exclude the next US market session. The origin canonical dataset's session date now governs both option and underlying future-path selection.
4. Final broader adjacent run: **174 passed, 2 subtests passed**, using `tools/run_governed_pytest.py` with an isolated repository-local base temp. The default Windows pytest temp directory was inaccessible; this was a harness permission issue, not a test failure.
5. `py_compile` and `git diff --check` completed without code errors. Only the newly created test temp folder was removed after the run.

## Behaviour now covered

- Future option observations are filtered by both quote and availability time at the evaluation cutoff.
- Market session comes from the canonical option-chain dataset, not an after-midnight UTC quote date.
- A post-midnight UTC assessment uses its source market session, so the next US session is not wrongly excluded.
- The option path retains only the exact OCC contract and excludes the assessment origin.
- Completed underlying bars require canonical observed time no later than the evaluation cutoff.
- Only observable horizons are labelled; immature horizons are not converted into zero returns.
- Re-running a mature family is idempotent; no provider call or capital authority is introduced.
- The orchestrator records an explicit `SKIPPED` option-capture status unless controlled activation is requested. If enabled, it performs at most 10 captures after scanning at most 100 previous-run families and reports a separate bounded-research receipt. Its failure cannot abort the Evening run or change a trade decision.

## Read-only real-data probe

The live control plane currently contains 12,337 DOI families, 90,998 assessments and zero option labels. In a read-only sample of 20 assessments from run `20260920_203115`, 10 had at least one later canonical observation for the same exact contract; the maximum observed future path in that sample was one session. This is a coverage probe, **not** a performance estimate or a representative random sample.

## Open before production acceptance

The bounded opt-in bridge is not a complete backlog scheduler. It cannot yet promise full option-label coverage across 90,998 historical assessments or 1–20-session horizons. Before enabling it for routine production, measure batch latency/database growth on a rollback-safe control-plane copy, implement resumable backlog scheduling with explicit coverage reconciliation, and verify correction/supersession when a partial option path is later backfilled. HARC and other fitted ranking models remain disabled.
