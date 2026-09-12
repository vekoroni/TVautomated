# AVS-FIX-002 Stage 0 claim sheet

**Design authority:** `docs/AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md` — FINAL v1.2  
**Baseline commit:** `cfa1a254459adb5150865cdbb36b6f5ba4c5beae` on `avs-fix-001`  
**Status:** STAGE 0 COMPLETE — STAGE 1 AUTHORISED  
**Production implementation changed:** No

## Verified claims

1. The complete v1.2 design and corrected developer/algorithm requirements exist as one governed authority pack under `docs/`; the Dropbox copies are compatibility pointers. Their SHA-256 identities are recorded in `STAGE0_BASELINE_MANIFEST.json`.
2. Six production entry points resolve to an import graph containing 138 local modules and 356 local dependency edges.
3. No reachable production dependency is untracked and no configured entry point is missing.
4. `control_plane.sqlite`, `historical_prices.sqlite` and `decision_outcome_ledger.sqlite` were snapshotted with SQLite's backup API.
5. All three production sources and snapshots pass `PRAGMA integrity_check`; table counts match and isolated restore copies were successfully opened and verified.
6. Pytest discovery is restricted to the governed `tests/` tree, preventing archived backup scripts from executing during release testing.
7. The governed test runtime is Python 3.14 with its native application packages, using `tools/run_governed_pytest.py` to load pytest without replacing native binary packages.

## Test evidence

- Stage 0 focused suite: **3 passed, 0 failed**.
- Complete governed baseline: **1,756 passed, 29 failed, 4 skipped, 286 subtests passed**.
- Three failing CDS history cases pass **3/3** when executed independently, proving suite-order contamination that must be repaired in the harness rather than represented as a product failure.
- The remaining baseline failures are retained in `BASELINE_DEFECT_REGISTER.md`; none is silently waived.

## Database recovery evidence

The authoritative design/requirement hashes, database sizes, integrity results and table-count comparisons are in `STAGE0_BASELINE_MANIFEST.json`. Snapshots are stored under `backups/avs_fix_002_stage0_20260912/databases/` and are not production inputs.

## Stage 0 exit decision

The Stage 0 exit gate passes because the design decisions are frozen, the import baseline is complete, database recovery is verified, the regression population is known and every baseline failure has a disposition path. Passing Stage 0 does **not** claim that the 29 baseline failures are resolved or that any v1.2 production functionality is implemented.

Stage 1 may implement provider finality and run-condition truth. A baseline failure may only be changed by a work-package claim that identifies the old assertion, new business rule and positive replacement test.
