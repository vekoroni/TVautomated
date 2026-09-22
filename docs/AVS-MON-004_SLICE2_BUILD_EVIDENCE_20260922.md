# AVS-MON-004 — Slice 2 build evidence

**Date:** 22 September 2026
**Scope:** resumable option-outcome scan, coverage reconciliation, and later-source correction.
**Production state:** implemented behind `AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED`; flag remains off. No provider API, live capture, model activation, or capital-authority change was made in this slice.

## Test-first result

- A later exact-contract quote initially produced no correction because a final label was treated as permanently complete. The new test failed before the append-only supersession path was added.
- The first bounded batch initially rescanned the same families on restart. Cursor and coverage tests failed before the scheduler was added.
- A disappearing subset of a previously complete quote path initially overwrote the result with a partial correction. The regression failed before the path-thinning guard was added.
- Focused suite: **29 passed**. Adjacent 11-suite regression: **162 passed, 2 subtests passed**. Python compilation and `git diff --check` passed.

## Implemented contract

1. The opt-in scanner stores a cursor after each family, including immature and no-change families. A crash before the cursor write replays the family idempotently. The scan has a frozen upper bound for its cycle and wraps to revisit prior families, including those that may receive backfilled quotes.
2. A changed outcome from later canonical observations appends a new immutable label with `supersedes_label_id` and `correction_reason`. The prior label remains queryable. The learning reader uses only one active label per assessment and horizon; unlinked conflicting final labels are excluded rather than arbitrarily selected.
3. A transient reader error or a strictly thinned subset of an already complete immutable option path does not revoke the prior valid label.
4. The batch receipt reports assessed population, expected assessment-horizon pairs, final distinct pairs, pending pairs, raw label rows, and per-horizon counts. It is a **coverage receipt**, not proof of a profitable strategy or complete historical paths.
5. The orchestrator checks at least 1 GiB free space before opt-in capture and labels the bounded batch separately from the trading pipeline. A capture failure does not grant authority or abort an otherwise valid Evening run.

## Read-only production baseline and limits

The live control plane was inspected read-only: approximately **4.76 GB**, **12,337 DOI families**, **90,998 assessments**, and **zero DOI outcome labels**. The volume containing it had approximately **61.6 GB free** at inspection. The first 100 schedulable family IDs took approximately **2.4 seconds** to fetch before adding the proposed scan index. These are capacity observations, not an enabled-run benchmark.

Routine activation is **not accepted yet**. The configured opt-in budget is at most 100 families scanned and 10 captured per Evening run; a single cycle over the present family population would require at least 124 such runs if every run scanned 100 families. The 1–20-session historical option paths are often incomplete, and no live-database index-build/WAL-growth or concurrent-writer test has been performed. Before routine activation, execute a controlled rollback-safe canary, benchmark scan and coverage queries, establish a throughput target, and verify that canonical exact-contract observations cover the required horizons. HARC/fitted ranking stays disabled.
