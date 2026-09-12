# DOI-10 — Intelligence Lab and Interpreter integration

**Date:** 2026-09-10  
**Status:** IMPLEMENTED — OFFLINE ACCEPTED  
**Production authority:** ADVISORY ONLY; human execution remains required

## Business outcome

DOI-10 closes the presentation gap that made an accepted four-row Interpreter
handoff look like the whole trading universe. The Intelligence Lab now uses the
complete governed opportunity book as membership and accepted handoff evidence
as an exact-identity overlay. Warnings, entry state, exit state, timing state,
liquidity state and DOI availability do not remove an opportunity.

## Delivered

- Pure DOI trader-projection contract with fixed `NONE` decision authority and
  `HUMAN_ONLY` execution authority.
- Read-only canonical resolver for the latest exact thesis/family/ranking and
  selected assessment.
- Explicit calibrated, deterministic, not-evaluated and unavailable states.
- Separate governed and DOI-preferred contract display with alignment status.
- Probabilities, uncertainty, model ID, evidence cutoff, dataset lineage and
  the full ranked alternative family in the final opportunity book.
- `lab_signal_book_v4_projection`: full v2 population plus validated v3 overlay.
- Intelligence Lab defaults to `ALL OPPORTUNITIES` and adds a DOI Ranking pane.
- Legacy EIL wording is presented as entry telemetry, not a trade command.
- Interpreter executable resolution remains accepted-handoff-only.
- New advisory full-book resolver permits only EOD review and trajectory use.
- Interpreter bundle validation rejects any DOI projection claiming decision or
  execution authority.

## Verification

- Focused DOI-10 tests: **8 passed / 0 failed**.
- Complete DOI-1 through DOI-10 standard-library regression: **115 passed / 0 failed**.
- Python compile: PASS.
- Browser inline-JavaScript syntax: PASS.
- Final-book field uniqueness: **474 / 474 unique**.
- Git whitespace/error check on the touched set: PASS.
- Current-run read-only rehearsal (`20260909_071646`):
  - full governed opportunities: **235**;
  - accepted actionable handoff rows: **4**;
  - accepted rows overlaid: **4**;
  - population preserved: **true**;
  - handoff hashes verified: **true**.
- Canonical control-plane SHA-256 before/after rehearsal:
  `0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc`.

## Honest limitation

The current production control plane does not yet contain activated DOI tables
or real DOI assessment/ranking rows. The existing book therefore projects
`DATA_UNAVAILABLE`, which is the correct non-fabricated state. The next newly
written book will contain the DOI fields automatically. Calibrated probability
claims remain unavailable until real DOI-7 outcome cohorts satisfy DOI-8 and
DOI-9 temporal acceptance gates.

The repository's existing `venv` points to a removed Windows Store Python and
the active Python has no `pytest`; consequently the separate historical
pytest-only MSI file could not be launched in this environment. DOI-10 includes
direct bundle-authority and live accepted-handoff rehearsals, but DOI-11 must
run the complete repository suite in a repaired test environment.

## Next phase

DOI-11 is controlled production acceptance: create one fresh completed-session
book, inspect the Lab projection, run the next valid Morning Gate, verify the
accepted Interpreter handoff and record the production release/rollback point.
