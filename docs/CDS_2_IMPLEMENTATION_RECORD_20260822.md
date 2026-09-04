# CDS-2 implementation record — 22 August 2026

## Outcome

CDS-2 is implemented and deployed in **write-through / active-read** mode.
Every successful full daily-OHLCV provider fetch made through the production
evening or morning launchers now updates the canonical historical-price
database before downstream use. Canonical OHLCV is now authoritative for the
guarded historical-price consumers; the legacy readers remain the rollback path.

The News Terminal and Pipeline Interpreter were not changed.

## Canonical database

- Path: `data/canonical/historical_prices.sqlite`
- Schema: `cds_historical_prices_v1`
- Current size: approximately 900 MB
- Current rows: 2,120,845
- Current tickers: 3,618
- Date range: 2021-08-23 through 2026-08-21
- Duplicate ticker/date/adjustment keys: 0
- Partial-session rows: 0
- SQLite integrity check: `ok`
- Schema and foreign-key validation: valid

The 2026-08-21 completed tail was recovered from the existing production
`data/daily` cache with zero network calls. It was not manufactured or forward
filled.

## Update contract

The current row key is:

```text
ticker + trading_date + adjustment_convention
```

On ingestion:

1. Dates and OHLCV types are normalized.
2. Structurally invalid bars are rejected.
3. Repeated source rows for the same calendar date are collapsed.
4. A missing key is inserted.
5. An identical key/value replay is recorded as unchanged and not duplicated.
6. A changed adjusted value is written to `ohlcv_daily_revisions` before the
   canonical row is replaced.
7. A partial current-session bar is stored as `PARTIAL` and excluded from
   default historical reads until a completed observation replaces it.
8. Every ingest has a batch record containing provider, source, run identity,
   row counts and timestamps.

The two seed revisions were EWH volume corrections on 2026-05-14 and
2026-05-15. OHLC prices were identical; both previous and replacement values
remain auditable.

## Offline migration

Source inventory:

- 1,655 reference-run package files inspected.
- 1,616 packages contained usable long OHLCV history.
- 39 packages had no OHLCV and were classified as source gaps.
- All 39 source-gap tickers were recovered from `data/daily`; canonical missing
  ticker count for this group is zero.
- All 3,615 `data/daily` CSV files were imported.
- 1,960 repeated calendar-date rows were normalized to one canonical row.
- Invalid observations after mixed-date normalization: 0.
- Network/API requests during migration and validation: 0.

Acceptance validation compared all 290,600 normalized daily-cache rows against
the canonical database and found zero OHLCV mismatches.

Reports:

- `data/canonical/reports/cds2_import_20260821_090928.json`
- `data/canonical/reports/cds2_validation_20260821_090928.json`
- `data/canonical/reports/cds2_lifecycle_shadow_20260821_090928.json`

## Provider and consumer integration

Write-through was added to full-OHLCV acquisition points:

- `polygon_data_fetcher.py`
- `garch_runner.py`
- `scripts/backfill_timeseries_into_packages.py`

Canonical read/shadow bridges were added to:

- Discovery
- package backfill/Vanguard package inputs
- GARCH
- Options historical closes

Options' existing MarketData close-only response is not written as OHLCV
because it lacks open, high, low and volume. In ACTIVE mode Options instead
reads closes from the complete canonical OHLCV record.

The incremental adapter retrieves only a missing head or tail range. Its test
proves one request for a missing tail and zero requests for a same-range replay.
It deliberately does not infer exchange holidays as missing internal bars.

## Production activation

The production orchestrator activates the following defaults when invoked with
`--evening`, `--morning` or the deprecated `--premarket` alias:

```text
AVSHUNTER_CANONICAL_DATA_ENABLED=1
AVSHUNTER_CANONICAL_WRITE_THROUGH=1
AVSHUNTER_CDS2_OHLCV_MODE=ACTIVE
AVSHUNTER_HISTORICAL_PRICE_DB=<repo>\data\canonical\historical_prices.sqlite
```

Consequences:

- New full historical-price fetches update the database.
- Canonical reads control the guarded historical-price calculations.
- A missing canonical ticker falls back to the legacy reader rather than
  fabricating data.
- Setting `AVSHUNTER_CDS2_OHLCV_MODE=SHADOW` restores legacy read authority
  while retaining write-through and parity observation.

The optional `run_evening.bat` and `run_premarket.bat` wrappers set the same
contract. Directly invoking an individual child-stage Python script outside the
orchestrator or these wrappers still requires the same environment flags if
write-through is desired.

## Lifecycle shadow replay

Reference run `20260821_090928` reconciled successfully:

| Stage | Tickers |
|---|---:|
| Discovery | 1,657 |
| Vanguard | 1,616 |
| Options | 1,374 |
| SuperBrain | 1,374 |
| EIL | 1,374 |
| GARCH | 1,374 |
| Morning | 1,129 |

The replay recorded 528 stage-drop events, zero stage re-entry events, and no
missing or unexpected worklist member at any stage. It made zero API calls.

## Tests and regression evidence

Twenty-two CDS-1/CDS-2 tests pass. Coverage includes:

- insert, replay, incremental tail and adjusted-history revision behavior;
- partial-session exclusion;
- schema, foreign-key and SQLite integrity;
- default-off behavior and explicit write-through activation;
- ACTIVE reads and SHADOW non-interference;
- missing-tail request reuse;
- launcher activation contract;
- registry/lifecycle/worklist/request-ledger regressions; and
- atomic payload interruption and concurrent registry clients.

All modified modules compile under Python 3.14. Four reference-run artifacts
remain hash-identical to the pre-CDS-2 baseline:

- final run manifest;
- package index;
- Options Intelligence summary; and
- Morning Gate summary.

`intelligent_orchestrator.py`, `morning_gate.py` and the universe scanner also
remain hash-identical to the CDS-2 pre-change baseline.

## Backup and rollback

Backups:

- `backups/cds_2_prechange_20260822`
- `backups/cds_2_shadow_activation_prechange_20260822`

Both contain SHA-256 manifests and verified copies. The source CSVs and package
histories were not modified or deleted, so the seed database is reproducible.

Fast operational rollback:

1. Set `AVSHUNTER_CANONICAL_DATA_ENABLED=0` and
   `AVSHUNTER_CANONICAL_WRITE_THROUGH=0`, or restore both launchers from the
   activation backup.
2. Leave the canonical database in place for forensic inspection.
3. If required, restore only the five guarded consumers from the pre-change
   backup and verify hashes; do not bulk-overwrite unrelated user changes.

## CDS-2 exit gate — accepted 24 August 2026

The build, migration, offline parity and lifecycle replay are accepted. The
already-fetched production cache from run `20260824_100301` was replayed through
the governed importer after the direct-orchestrator activation repair. The
database advanced from 2026-08-20 to 2026-08-21.

Acceptance results:

- 3,615 daily-cache files processed;
- 3,005 missing bars inserted;
- 1,082 changed overlaps captured in the revision audit;
- 289,518 observations unchanged;
- zero network calls, rejected rows, source gaps or importer errors;
- zero daily parity mismatches after import;
- zero duplicate canonical primary keys;
- SQLite integrity `ok` and schema valid;
- 25 CDS-1/CDS-2 regressions pass; and
- the pre-import backup hash exactly matches the recorded live pre-change hash.

Reports:

- `data/canonical/reports/cds2_pre_exit_validation_20260824.json`
- `data/canonical/reports/cds2_exit_import_20260824_100301.json`
- `data/canonical/reports/cds2_exit_validation_20260824_100301.json`

The production default is therefore promoted from `SHADOW` to `ACTIVE`.

### 24 August production-gate attempt

Run `20260824_100301` completed with pipeline technical health `PASS` and a
health score of 97. Backfill obtained usable Polygon history for 1,599 tickers,
including the completed 2026-08-21 session, but the canonical database recorded
zero ingest batches for that run and remained capped at 2026-08-20.

The write-through code did not fail. The run was executed by
`C:\Python314\python.exe` without the launcher-owned CDS environment. The
repository virtual-environment executable configured by the launchers was
present but unusable, which had encouraged direct Python invocation and thereby
bypassed the disabled-by-default activation flags.

The operational production command is:

```text
python intelligent_orchestrator.py --evening
```

The orchestrator now activates the governed CDS-2 environment itself before
starting either the evening or morning workflow. Consequently every child
stage inherits write-through/active-read settings without depending on a batch
wrapper. Explicit environment values remain authoritative so the documented
rollback switches still work.

Both optional production launchers also:

- verify that the preferred virtual-environment Python can import `pandas` and
  `pyarrow`;
- fall back to the first working system Python when it cannot;
- print the selected interpreter and canonical database path;
- fail closed unless the three CDS activation flags have their governed values;
  and
- support `--cds-launcher-self-test`, which validates startup without invoking
  the evening or morning pipeline.

Both launcher self-tests pass using `C:\Python314\python.exe`. A direct
orchestrator startup regression also proves that the normal `--evening`
command enables CDS write-through in `ACTIVE` read mode and that a spawned child
process inherits the same contract, without executing the pipeline. The
combined CDS-1/CDS-2 suite passes 25 tests. The controlled exit replay advanced
the database and the accepted post-import report closes the CDS-2 gate.
