# AVS-INT-001 A1 — governed invalidation alias receipt

**Status: IMPLEMENTED_PENDING_LIVE_ACCEPTANCE.** This is a row-level data
lineage repair, not a change to ticker direction, quote timing or capital
authority. The operator starts the Evening run; this work made no provider or
broker call and did not modify either database or the universe.

## Source-to-consumer correction

`contracts/lab_control.py` already resolves `invalidation_price` through
`_book_invalidation`, which checks the directional side against the thesis
reference spot. The final Lab field contract omitted `invalidation_spot`,
although that exact alias is expected by downstream handoff consumers. It is
now published only when the resolved price is positive, the state is
`AVAILABLE`, and the authoritative source is present. Provenance records that
the alias came from the side-checked book invalidation. If the stop is absent,
wrong-side or unattributed, the alias stays blank and the directional row
cannot be labelled tradeable; the opportunity remains visible for review.

The read-only 25 September TEST run has 1,549 Lab rows, 1,180 with a numeric
`invalidation_price`, all 1,180 `AVAILABLE` and source-attributed. The Morning
candidate file has 175 directional rows without `invalidation_spot`; joining
their ticker to the validated-trades file shows all 175 in
`STAND_DOWN_UPSTREAM_AUTHORITY`. This repair does **not** fabricate a stop for
those rows or reinterpret the run as a live acceptance result.

TDD: four regression cases failed before the field was added, then the
alias/source/side tests and affected Lab golden and governed-handoff tests
passed (30 tests). The expanded affected cross-pipeline suite passed
**154 tests, 1 skipped and 3 subtests**. A normal completed-session run
remains the live acceptance gate. In the operator's next run,
verify that actionable rows have a source-qualified stop, all review rows are
retained, selected-handoff missing counts reconcile by route, and the Lab
projects the alias without changing the frozen Evening thesis.
