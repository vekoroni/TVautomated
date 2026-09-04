# CDS-0 and CDS-1 implementation record — 22 August 2026

## Outcome

CDS-0 and CDS-1 are implemented as an isolated control plane. The existing
AVSHUNTER production pipeline is unchanged and does not import or invoke the
new package. All activation flags default to disabled.

## CDS-0 — completed

- Baseline creator: `tools/create_cds_baseline.py`
- Verified baseline: `backups/cds_0_1_prechange_20260822`
- Production/reference files copied and SHA-256 verified: 13
- Current-to-baseline hash mismatches after CDS-1 implementation: 0
- Secrets, environment files, databases, Parquet payloads and bulk histories
  were intentionally excluded from the code backup.
- The baseline manifest records repository status, source and backup hashes,
  reference run ID `20260821_090928`, and restoration instructions.
- No data was deleted or pruned.

## CDS-1 — completed

Implemented components:

- `canonical_data/contracts.py`: dataset type, scope, freshness, provenance and
  exact/superset/partial/miss resolution contracts.
- `canonical_data/registry.py`: WAL-mode SQLite registry, explicit schema
  initialisation, schema validation, run metadata, immutable dataset identity,
  provenance and lookup indexes.
- `canonical_data/lifecycle.py`: versioned ticker lifecycle, legal transitions,
  explicit terminal reactivation, stage/capability authorization, governed
  worklists and reconciliation.
- `canonical_data/request_ledger.py`: logical request, physical request and
  retry accounting; blocked requests and cache misses record zero HTTP calls.
- `canonical_data/storage.py`: path-safe, hash-verified atomic payload writes,
  idempotent reuse, conflict rejection and atomic Parquet promotion.
- `canonical_data/gateway.py`: resolver-only authorization boundary. CDS-1 has
  no provider adapter and therefore cannot issue API calls.
- `canonical_data/feature_flags.py`: all CDS behaviour is disabled by default.
- `tools/validate_canonical_data.py`: explicit registry initialise/validate CLI.

Feature flag defaults:

```text
AVSHUNTER_CANONICAL_DATA_ENABLED=0
AVSHUNTER_CANONICAL_WRITE_THROUGH=0
AVSHUNTER_STAGE_GATING_ENFORCED=0
AVSHUNTER_CANONICAL_OFFLINE_REPLAY=0
```

Within the new gateway, lifecycle authorization is always a safety invariant.
The stage-gating flag controls future pipeline adoption; it does not permit an
unauthorized provider request inside CDS.

## Verification

Command:

```powershell
C:\Python314\python.exe -m unittest tests.test_canonical_data_system -v
```

Result: 14 tests passed.

Coverage includes:

- default-off activation flags;
- scope normalization and stable fingerprints;
- exact, superset, partial and stale/miss resolution;
- provenance and immutable dataset IDs;
- legal, illegal and stale-version lifecycle transitions;
- terminal-drop API suppression and explicit reactivation;
- authorized worklist generation and reconciliation;
- blocked, cache-hit, cache-miss, physical-call and retry accounting;
- concurrent registry clients under SQLite WAL/single-writer behavior;
- idempotent atomic payload reuse and conflict rejection;
- simulated interrupted replacement preserving the prior payload;
- hash-checked atomic Parquet promotion; and
- path traversal rejection.

Python compilation also passed for the full `canonical_data` package and its
test module. The repository virtual environment points to an unavailable
Windows Store Python 3.13 executable, so the tests were written against the
standard-library `unittest` runner and executed with the available Python 3.14
runtime. No package was installed and no dependency configuration was changed.

## Production and rollback boundary

No existing production script, launcher, database, run output or Pipeline
Interpreter component was changed. No live registry or canonical payload store
was created. CDS-1 becomes active only if a future phase explicitly wires it
into a producer and enables its feature flags.

Rollback is removal of the new `canonical_data` package, its focused test and
validation tool. If an existing file ever needs restoration, use the CDS-0
manifest and verify its SHA-256 hash after copying the corresponding file from
the baseline. Do not bulk-restore over unrelated user changes.

## Deliberately deferred to CDS-2 and later

- Measurement/import of existing OHLCV caches.
- Polygon or other provider adapters.
- Shadow integration with Discovery, GARCH, Backfill or Options Intelligence.
- Production worklist enforcement.
- Option-chain, contract-reference, sector-derived and live/morning namespaces.
- Removal of any direct provider call.

The next safe step is CDS-2 shadow measurement and canonical OHLCV import. It
must keep production reads unchanged while comparing canonical decisions and
API-call counts against the current pipeline.
