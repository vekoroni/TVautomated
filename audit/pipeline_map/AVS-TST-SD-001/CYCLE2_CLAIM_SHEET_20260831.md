# AVSHUNTER Cycle 2 Claim Sheet

Date: 2026-08-31  
Baseline commit: `5d886f07c1d290f25600e2e7e62ae77aad85476a`  
Release state: **IMPLEMENTED — AWAITING FRESH EVENING/MORNING ARTEFACT VALIDATION**

This sheet identifies only the Cycle 2 work completed in this increment. The
repository was already materially dirty before work began (72 modified, 32
deleted and 130 untracked paths in the Cycle 1 intake), so no assertion is made
that the repository as a whole is reproducible from the baseline commit.

## Backup and rollback claim

- Backup root: `backups/cycle2_prechange_20260831_221858/`
- Backed-up lifecycle database SHA-256:
  `7cdc59af8521a51c1ba8a63ff38756dd7e73f1f3dc25eb373bfec4c81db724a8`
- The backup database remains 39,067,648 bytes and was not modified.
- Rollback is a controlled restore of the affected files and the three SQLite
  files (`control_plane.sqlite`, `-wal`, `-shm`) from that directory while all
  AVSHUNTER writers are stopped.

## Claims

| Claim | Implementation | Verification | Status |
|---|---|---|---|
| C2-01 Governed hold invariant | Lifecycle accepts only routed 5, 10 or 20-session holds. Other values fail closed. | Boundary tests cover 0, 7, 8, 15 and 100; valid 10-session calculation retained. | PASS |
| C2-02 Directional invalidation invariant | CALL invalidation must be below thesis spot; PUT invalidation must be above it. Wrong-side and zero-distance geometry raise before classification. | Symmetric CALL/PUT tests added. | PASS |
| C2-03 No fabricated invalidation | Removed Options Intelligence 3% stop, EOD ATR/3% stop, legacy alias use in Exit Rules and wrong-side stop mirroring. | Missing-stop, EOD, exit-rule and Morning Gate fail-closed tests added. | PASS |
| C2-04 Explicit non-directional state | STRANGLE/other non-directional rows return `NOT_EVALUATED_NON_DIRECTIONAL`/`NOT_APPLICABLE`; they are not treated as PUT or as a data defect. | Adapter and exit-plan tests added. | PASS |
| C2-05 Central state vocabulary | Added `contracts/governed_states.py` and used canonical data/evaluation literals at the changed handoffs. | Vocabulary uniqueness/stability tests added. | PASS |
| C2-06 Append-only correction lineage | All three lifecycle tables now carry `calculation_version`, `supersedes_event_id`, `correction_reason`, `corrected_by_run_id`, and `correction_state`. Partial lineage fails closed. | New-schema, migration, complete-lineage and partial-lineage tests added. | PASS |
| C2-07 Immutable legacy correction | Corrected OLM2 thesis events can supersede a legacy terminal event without altering that event. | Test proves legacy `INVALIDATED` row is unchanged and successor points to its event ID. | PASS |
| C2-08 Live schema migration | Existing control-plane DB migrated additively from v1 to v2. | SQLite integrity `ok`; counts unchanged; five columns on all three tables; six append-only triggers retained. | PASS |
| C2-09 Regression correction | Fixtures now use governed `invalidation_spot`; import no longer replaces/closes test-host streams. | Focused and governed regression suites pass. | PASS |

## Test evidence

- Syntax compilation: 7 changed production modules, PASS.
- Focused Cycle 2 suite: **104 passed, 0 failed**.
- Governed regression battery: **234 passed, 0 failed, 1 deselected,
  3 unittest subtests passed** across the established 17 OLM suite files plus
  the three Cycle 2 governance suites.
- The one deselected check launches Options Intelligence in a child process.
  Codex cannot execute the Windows Store Python 3.13 interpreter referenced by
  the production venv. The in-process Options Intelligence and direct contract
  tests pass; this is recorded as an environment validation still required in
  the user's normal PowerShell account.
- An all-repository test collection was attempted. It contains unrelated
  environment/external-fixture suites and is not the governed Cycle 2 release
  battery. It was not used to conceal or override the clean scoped result.

## Live database evidence

Before and after row counts are identical:

| Table | Before | After |
|---|---:|---:|
| `option_thesis_events` | 1,507 | 1,507 |
| `option_contract_observations` | 1,021 | 1,021 |
| `option_contract_selection_events` | 1,021 | 1,021 |

All existing rows are explicitly identified as
`option_liquidity_lifecycle_v1`. New writes use v2 calculation versions. The
current live database SHA-256 after migration is
`a2a68a951b159c1ae72b3c72e9e07d020f64c799ca3c72cacd255e9b91fb1ee2`.

## Acceptance boundary

Cycle 2 code and schema are deployed. Production-cycle acceptance is not yet
claimed because no fresh post-change evening output and subsequent Morning Gate
output exist. The next controlled evidence is one manual evening run, followed
by the Morning Gate during a valid market session, then artefact reconciliation
for hold values, invalidation geometry, non-directional states and supersession
lineage.
