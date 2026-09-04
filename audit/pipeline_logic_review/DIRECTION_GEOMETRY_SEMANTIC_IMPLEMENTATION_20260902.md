# Direction, Geometry and Semantic Handoff Implementation Record

**Date:** 2026-09-02  
**Status:** Code implemented; focused regression passed; fresh evening/morning production evidence pending.

## Backup

Pre-change files were copied to:

`backups/20260901_direction_geometry_semantic_prechange/`

No database schema or production run artefact was changed.

## Implemented changes

1. Discovery now resolves the thesis direction using Fusion, Wyckoff, reconciled Precor intent and dominant trend.
2. Opposing structural directions fail closed as `UNRESOLVED / CONFLICT_REVIEW`.
3. Fresh Discovery output marks direction authority as `DISCOVERY_GOVERNED`.
4. Options preserves the frozen Discovery direction and disables later non-directional resolution for that governed record.
5. Pre-v1.2 artefacts retain an explicitly labelled compatibility adapter.
6. Side-aware invalidation selection is centralized in `contracts/thesis_geometry.py`.
7. Invalidation precedence is governed Discovery -> Wyckoff validator -> non-ATR structural stop -> explicit invalidation.
8. ATR fallback stops are not promoted to authoritative thesis invalidations.
9. PUT and CALL targets and fallback R multiples are side-aware.
10. Critical EOD numeric missingness remains `None` instead of becoming `0.0`.
11. Manifest health now publishes semantic coverage independently of technical completion and cannot remain 100 when EV3 reports selected-handoff defects.
12. Intelligence Lab now reads governed `time_horizon`, `hold_period` and `planned_hold_sessions` before falling back to contract DTE.

## Files changed

- `contracts/direction_governance.py`
- `contracts/thesis_geometry.py` (new)
- `avshunter_discovery_ULTIMATE.py`
- `scripts/avshunter_options_intelligence.py`
- `eod_candidate_engine.py`
- `contracts/lab_control.py`
- `intelligence-lab/intelligence_lab.py`
- `tests/test_direction_geometry_semantic_repairs.py` (new)

## Test evidence

- Python syntax compilation: PASS for all changed Python files.
- New focused suite: 9 passed.
- Cross-boundary direction/Options/EOD/Morning/Lab regression: 163 passed, 2 deselected, 3 subtests passed.
- Additional manifest/Lab readiness pack: 13 passed.
- Total reported executions: 185 passed plus 3 subtests; no functional test failure.

Two tests were deselected because the repository venv points to an inaccessible WindowsApps Python 3.13 interpreter:

- direct-file launch environment test;
- one native SciPy IV solver test.

The native solver test was not changed by this implementation. All other tests in its file passed using an import-only SciPy shim; real numerical tests must still be run in the repaired production venv before release certification.

## Static replay against run 20260901_082437

Direction projection:

- Existing: CALL 14, PUT 64, UNRESOLVED 1,440.
- New rule: CALL 602, PUT 556, STRANGLE 185, UNRESOLVED 175.
- Explicit conflict review: 29.

Side-aware invalidation projection:

- CALL: 439 valid, 163 missing.
- PUT: 525 valid, 31 missing.
- 964 values resolved from `WYCKOFF_VALIDATION`.

This replay proves deterministic behavior against stored evidence; it is not a substitute for a fresh production run.

## Production acceptance still required

1. Repair or recreate the Python 3.13 virtual environment and run the complete unmodified regression suite.
2. Run `python intelligent_orchestrator.py --evening` through the normal production command.
3. Confirm Discovery direction/status counts and governed invalidation coverage.
4. Confirm Options does not reverse `DISCOVERY_GOVERNED` rows.
5. Confirm the EOD book contains both CALL and PUT candidates with blank—not zero—missing invalidations.
6. Confirm manifest technical and semantic health are shown separately.
7. Run the following Morning workflow through the orchestrator, including the finalizer.
8. Confirm Lab Horizon/Hold values match the governed opportunity book.

Do not reuse a pre-v1.2 EOD run for production acceptance because its direction records have the prior calculation version and authority contract.
