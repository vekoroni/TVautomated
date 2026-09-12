# DOI Phase 1 implementation record — 2026-09-10

## Scope

Implemented the authority-decoupling and non-discard slice from
`AVS-SD-DOI-001` version 1.1. This release does not yet implement learned
liquidity or monetisation probabilities.

## Production behaviour

- EIL always runs as advisory evidence (`LIVE_MODE = False`).
- EIL `BLOCKED` no longer vetoes a Lab row, blocks a handoff packet, creates an
  orchestrator handoff conflict, removes a Morning candidate, or disappears
  from Interpreter triage.
- EIL no longer contributes to EOD structural tier or monetisation score.
- EIL output failure is an advisory coverage issue, not a fatal run flag.
- Missing contract economics, wide spread and option-repair conditions produce
  monitor/review states rather than candidate deletion.
- Missing invalidation remains prominently disclosed as data-insufficient, but
  its row is retained.
- A blocked or monitor-only horizon becomes advisory
  `HORIZON_ELAPSED_REASSESS`/`HORIZON_MONITOR_ONLY` evidence and no longer
  short-circuits enrichment.
- Every produced candidate carries `doi_decision_authority=NONE`,
  `execution_authority=HUMAN_ONLY`, and
  `opportunity_retention_policy=PRESERVE_AND_DISCLOSE`.

## Verification

- Python compilation: PASS for all seven affected production modules.
- Focused release regression: 94 passed plus 69 parameterised subtests.
- Full repository suite: 1,571 passed, 4 skipped, 30 failed.
- The 30 full-suite failures are outside the DOI Phase 1 change paths. Most are
  historical MSI audit tests intentionally asserting that later MSI features
  are absent; three are date-sensitive CDS backfill fixtures and one is a
  pre-existing UI label check.

## Rollback evidence

Pre-change production files are in `backups/doi_phase1_20260910`.
The canonical lifecycle database was copied before DOI-2 work to
`control_plane.pre_doi2.sqlite`; source and backup SHA-256 matched at copy time:
`0F725C01208A427818EBF49C6F964DE12610ED3A21010DDDE4081D564629CFDC`.

## Acceptance state

DOI-1 is implemented and offline-accepted. A production pipeline run is still
required to measure the population invariant on real artefacts:

`governed opportunities before EIL = governed opportunities after EIL`

The run must also confirm that EIL telemetry remains populated while no EIL,
entry, exit, spread, liquidity or horizon value removes a row.

