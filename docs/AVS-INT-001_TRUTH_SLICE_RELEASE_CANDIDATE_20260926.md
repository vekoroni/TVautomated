# AVS-INT-001 — truth-slice release candidate, 26 September 2026

**Status: IMPLEMENTED_PENDING_LIVE_ACCEPTANCE.** This is not a claim that the
full INT-001 programme or a production Evening/Morning cycle has passed.
The operator alone starts the Evening run. No pipeline run, provider request,
broker order, database maintenance, universe edit, model activation or research
deletion was performed in this slice.

## Business effect and production callers

| Confirmed issue | Production correction | Boundary |
|---|---|---|
| The Evening thesis compared a 6–10- or 11–20-session target with only the *increment* for that band | `domain/pretrade_focus.py` now prefers the canonical cumulative 5/10/20-session fraction, or sums complete legacy increments. `contracts/lab_control.py` carries the canonical budget into the Lab book. An invalid canonical value or contradictory convention does not silently fall back. | This is an advisory target-feasibility review, not a trade gate, probability or forecast validation. |
| The Lab could show a numeric convexity score with no calculation source or scale, and then invent a source from matching numbers | The book and live Lab read model now publish an aggregate score only when its eight-condition source, scale and number reconcile. Otherwise the UI shows `UNAVAILABLE · SOURCE NOT VERIFIED` and retains the underlying thesis and component data. | OI/Superbrain producer heuristics and the unvalidated GARCH bias remain separate open work; no score is promoted merely by stamping a source. |
| The Lab JS export suite crashed before assertions on an existing publication timer | The test browser stub implements a non-firing `setInterval`, allowing the real inline Lab script and export mapper to be exercised. | No production timer behaviour changed. |

## TDD and replay evidence

- The original 6–10D and 11–20D expected-move tests failed before the repair; canonical-invalid and contradictory-convention cases also failed red before the strict fallback fix. The convexity verdict-encoding case failed red before source validation.
- Focused Evening/Morning tests: **29 passed**. Broader Lab/GARCH selection: **65 passed**. After resolving the explicit additive-book schema assertion and JS harness issue, the final affected integration suite: **137 passed, 1 skipped, 3 subtests passed** (including the read-only horizon-audit helper). No hidden failed tests are counted as green.
- Read-only stored-book command: `C:\Python314\python.exe tools\avs_int001_horizon_audit.py data\output\runs\20260925_061649\intelligence_lab\final_opportunity_book_20260925_061649.json`. The file belongs to a `TEST` run and was not rewritten. Of 1,549 rows, 334 had comparable 6–10D target and move data; **88** had a legacy-only target-beyond-review-band flag. This is an arithmetic sensitivity result, not a reconstructed Evening bucket or realised return. Another 101 6–10D rows were not comparable. No 11–20D rows occurred in that stored book.
- The prior stored book had 1,549 numeric convexity scores and zero source qualifiers. The new Lab projection discloses those as unverified instead of displaying a measured aggregate; it does not delete the candidates.

## Release boundaries and next acceptance

The full INT-001 design still has open slices: selected-handoff geometry and
semantic tradeability at the right row grain; source repair/held-out validation
of GARCH and convexity producers; exact-contract 5–20-session outcome coverage;
and any WAR v2 or learned ranking activation. The six local WAR v2 components
are untracked/unwired research and are deliberately not part of this release.
Worker 3 remains disabled; capital allocation and order authority remain off.
These are not disguised as passing fixes.

Before calling this slice production-accepted, the operator's normal
completed-session Evening run must reach its terminal success marker with no
later abort; the final manifest, macro publication, selected contracts, row
counts, cumulative fields and Lab projection must reconcile. Morning then
requires its own terminal marker and full-book event/contract joins. A live
browser check should confirm blank-not-zero convexity and correct target-review
language. A candidate CSV alone is not completion. If any check fails, stop
promotion, preserve the run and repair only the confirmed defect. The tested
code can be committed as a bounded truth slice; a release tag/sign-off waits
for live acceptance.
