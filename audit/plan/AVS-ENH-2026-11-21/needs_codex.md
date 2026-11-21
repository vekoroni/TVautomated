# AVS-ENH-2026-11-21 — items for Codex

21 November 2026. Wave 0 only. Codex owns the Lab, the pipeline and macro.

## Nothing in Wave 0 needs a Codex change

All eight Wave 0 items (F-01 to F-05, F-09, F-10, F-29) are Lane B. None needs a new Lab field.

## Related items already with Codex

| Brief item | Why it matters to Wave 0 | Where it stands |
|---|---|---|
| F-11: Evening still in progress at 10:00 UTC, so the scheduled triage did not run | A late Evening pushes triage, deep dives and tickets later, which is one reason preparation is missed | The legacy Interpreter switch-off (BF-03) is in build and is expected to shorten the Evening. A stage timing log (I-06) is not planned yet. |
| F-09: `macro_state.json` | Wave 0 flags the stale file. A dependable source for the day's kill switches would come from the macro side | Not requested yet. Depends on ACK's answer to question 4 in `plan.md`. |

## For the later waves (not verified yet)

These items of the brief are marked Lane A or shared, and will need Codex once verified: F-23 (sector mapping), F-24 (contract fallback from Lab alternatives), F-25 (deal-pinned and stock-gate flags), F-26 (half-target valuation clock), F-27 (side on reversal days), F-28 (hold beyond 20 sessions), and Part C phase 3.

## Ownership point for ACK

The brief gives the pipeline to Codex. On 21 November ACK had Claude Code build three pipeline fixes: advisory packets never stop the Evening (`c8631c4`), the 30-day IV benchmark on every chain path, and the forecast runner's Discovery worklist (both uncommitted). Those stand as instructed; future pipeline items need a named builder so two tools do not edit the same file.
