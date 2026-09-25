# Amendments to the change register (25 September 2026, after review)

The register `CHANGE_REGISTER_AND_IMPACT_20260925.md` could not be edited in place (file locked by a viewer), so its amendments sit here and override its text. Full reasoning: `REVIEW_RESPONSE_CHANGE_REGISTER_20260925.md`. The register stands as a **research backlog**, not a production release plan.

| Section | Amendment |
|---|---|
| A1 / G | Of the 375 rows missing an invalidation, 312 also lack a target: the fallback can complete at most 63. Rows with both target and invalidation today: about 1,108, not "~530". All 375 were BLOCKED, none GO. "Degenerate" is defined relative to the vol budget (inside 0.25 × the hold-window move), not a fixed 1%. The Wyckoff fallback needs a side-and-age validity test before approval |
| A2 / D1 | `NO_EXECUTABLE_EXPRESSION` becomes the reversible per-session state `NO_CURRENT_EXECUTABLE_QUOTE`. D1 is restated as four axes (thesis state, data sufficiency, expression/quote state, research rank), each with its own states; hard correctness and data-quality checks are retained; only advisory verdicts move to display. `NO_POSITIVE_EDGE` is a research-rank state, not a death, until C3 and C4 pass |
| B2 | Not tonight's active selector. Tonight: B1 repaired and the shadow family broadened; legacy selection stays authoritative; old and new choices and quotes recorded. Activation only after pre-registered acceptance on matched prospective cases. "Improves" reworded: lowers model-implied expression cost; creates no edge (positive rows 24 → 19) |
| B3 | Long shares in shadow for BULL theses first. Short shares are in spec §10 (subject to borrow) but wait for borrow data. The funnel line "714 → ~1,100 valuable expressions" is withdrawn: shares add an expression to assess, they do not recover rows |
| C1–C2 | "Probability-free" reads "thesis-probability-free, distribution-assumed". p\* is review information, not a gate, and a two-outcome lower bound until the three-class version exists. Thresholds are frozen for a later untouched cohort |
| C3–C5 | C3 precedes any value-based promotion. C4 pairs with A3 before any monetisation claim. C5 activates only after C4 |
| E1–E2 | Convexity score hidden; gamma and macro shown with source, timestamp, quality and limitations rather than hidden |
| F1 | Cohort 1 is a shadow comparison cohort (current selector versus broad family); activation only after pre-registered acceptance tests |
| G, wording | "Median expectancy" reads "model-implied scenario value" throughout. "30–50 probable" reads "unverified target for future calibration". The "Probable, once validated" and "valuable expression" rows of the funnel table are withdrawn |
| H | Release sequence replaced by the reviewer's four steps (response document §3) |
| Governance | All research files of 25 September are untracked; ACK to commit the revised versions before any item is treated as a release requirement |
