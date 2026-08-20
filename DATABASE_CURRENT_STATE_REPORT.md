# AVSHUNTER Database Current-State Report

Discovery only. No fixes, no recommendations, no schema changes were made in
producing this report. Every non-trivial claim below carries a confidence
percentage; observation is distinguished from inference throughout. No
credential value is reproduced anywhere in this document.

**Architectural fact that shapes everything below (confidence 100%,
filesystem-verified):** what look like "two separate repositories" are
cross-wired by two Windows symlinks:
- `C:\Users\ACKVerissimo\vanguard\vanguard` → `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\vanguard` — the real `vanguard` Python package (`main.py`, `layer2_statistical/`, `config.py`) physically exists only inside the `AVSHUNTER-Intelligence` git repo.
- `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\vanguard\data` → `C:\Users\ACKVerissimo\vanguard\data` — the physical parquet/sqlite data files exist only under the standalone `vanguard` repo's untracked `data\` directory.

So there is exactly **one** physical `vanguard` package and **one** physical
data directory; each repo holds one half and reaches the other only through
the symlink. The standalone `vanguard` repo (remote `TVautomated`) has a
single commit (`0c40e42`) and tracks exactly 3 files: `.gitignore`,
`scripts/enrich_actuarial_9dim.py`, `scripts/polygon_actuarial_builder.py`.

---

## Summary table

| Store | Format | Size | Rows | Date range | Git tracked | Identified writers |
|---|---|---|---|---|---|---|
| `vanguard/data/actuarial_database_v6.parquet` | Parquet | 870,399,668 B | 6,033,072 | 2021-03-30 → 2026-06-24 | No | 4 candidate writers (see Part 2); direct default-path writer confirmed for 1 of them |
| `vanguard/data/actuarial_database*.parquet` (21 siblings: v1–v6 variants, backups, rebuilds) | Parquet | 197 MB – 870 MB each | 3.0M – 6.0M each | mostly 2021-03-30 → 2026-01/04-2026 | No | Same lineage, see Part 2 |
| `vanguard/actuarial_checkpoint_{200..3200}.parquet` (16 files) | Parquet | 422 KB – 13.1 MB | partial | n/a (mid-build checkpoints) | No | `avshunter_db_update.py` |
| `vanguard/data/actuarial_cache.parquet` | Parquet | 299,845 B | 871 | n/a (state-keyed cache) | No | `actuarial_cache_builder.py` |
| `vanguard/data/behaviour_cache.parquet` | Parquet | 38,511 B | 462 | n/a | No | `scripts/behaviour_cache_builder.py` |
| `AVSHUNTER-Intelligence/data/actuarial_db.sqlite` | SQLite (nominal) | **0 B** | N/A — no valid header | N/A | No, never | **None found** |
| `vanguard/data/actuarial_db.sqlite` | SQLite (nominal) | **0 B** | N/A — no valid header | N/A | No, never | **None found** |
| `AVSHUNTER-Intelligence/data/cache/iv_history_cache.db` | SQLite 3 | 471,040–573,440 B (size moved between snapshots, see Part 1) | `iv_history`=5,650; `iv_cache_meta`=431; `options_vol_history`=215 | 2025-08-04 → 2026-07-31 | No | `scripts/avshunter_universe_scanner.py` (tracked, but has uncommitted local edits) |
| `AVSHUNTER-Intelligence/data/journal/trade_journal.db` | SQLite 3 | 1,581,056 B | `trades`=0; `closed_trades`=14; `calibration_reports`=10 | 2026-03-06 → 2026-07-18 | No | `avshunter_trade_journal.py` (primary); `outcome_capture.py`, `confirmation_ingester.py` (indirect) |
| `.../journal/archive/trade_journal_pre_open_trade_clear_20260511_231243.db` | SQLite 3 | 262,144 B | `trades`=2; `closed_trades`=3 | 2026-03-06 → 2026-04-27 | No | No writer script located — mechanism unknown |
| `AVSHUNTER-Intelligence/data/phantom/phantom_history.db` | SQLite 3 | **16,085,766,144 B (~16.1 GB)** | `chain_snapshots`≈18.42M; `options_greeks_history`≈17.76M (both rowid-bound proxies, see Part 1); several smaller tables exact | `chain_snapshots`: 2021-05-28→2026-06-26 (sampled); `options_greeks_history`: 2024-05-17→2026-07-17 (sampled) | Partially — 2 of ~9 writer scripts tracked | See Part 2 |
| `.../phantom/phantom_history.pre_marketdata_update_20260725_065732.bak.db` | SQLite 3 | 15,138,578,432 B (~15.1 GB) | Same schema, ≈947 MB smaller than live | Snapshot as of 2026-07-23 | No | Backup — no writer script located |
| `AVSHUNTER-Intelligence/config/hybrid_universe_enhanced.csv` + 3 `tickers*.csv` variants | CSV | up to 273,748 B | ticker universe lists | n/a | No | Multiple discovery/repair scripts |
| `AVSHUNTER-Intelligence/data/daily/` | 6,567 individual per-ticker CSVs | 74 MB total | per-ticker OHLCV | n/a | No | Not traced in detail (out of named scope, flagged for completeness) |

No `.duckdb`, `.h5`, or `.feather` file was found anywhere in either repository (confirmed by an explicit extension sweep, excluding `_cleanup_holding/`, `venv/`, `site-packages/`).

---

# PART 1 — Inventory

## The actuarial parquet family

**`actuarial_database_v6.parquet`** — the live store, path `C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v6.parquet` per `vanguard/config.py::ACTUARIAL_DATABASE_PATH`. 870,399,668 bytes, mtime 2026-07-25 07:12:51, 6,033,072 rows, 55 columns (7 Parquet row groups, snappy-compressed). Untracked in both repos; matched by `vanguard/.gitignore`'s `*.parquet` rule. No identical-content copy found in a bounded search of the pipeline repo's `data/`, OneDrive, or Dropbox (confidence 85% — bounded, not exhaustive).

**Column-count anomaly, confidence 70% on cause:** column 51 of 55 is `__index_level_0__` (int64, 6,033,072 distinct values = row count) — the standard artifact of a pandas `.to_parquet()` call made without `index=False`. Of the writers that touch this file, only `add_early_candidate.py:11` omits `index=False`; the other three pass it explicitly.

**21 sibling files** in `vanguard\data\` (v1 through v6 variants, `_updated`, `_enriched`, `_pre_clean`, `_pre_enrich`, multiple `_pre_*`/`.bak` backups, plus two files not in any prior inventory — `actuarial_database.parquet.backup`, 197,601,372 B, mtime **2026-02-19**, the earliest surviving snapshot in the family, and `actuarial_database.parquet.bak`, 388,315,832 B, mtime 2026-03-01). All untracked, all `.gitignore`-matched. Row counts range 3.0M–6.0M; column counts 22–55, tracking the schema's growth over time. **Three byte-identical pairs confirmed by MD5** (not just matching size):
- `actuarial_database.parquet` == `actuarial_database_updated.parquet`
- `actuarial_database_v6_full_rebuild_20260517_v2.parquet` == `actuarial_database_v6_pre_9dim.parquet`
- `actuarial_database_v6.backup_20260518_pre_full_rebuild_v2.parquet` == `actuarial_database_v6.pre_full_rebuild_20260517_093620.bak.parquet` (also identical mtime to the millisecond — the "filename says 0518, mtime says 0517" oddity resolves to this being the same physical backup under two names).

**16 checkpoint files** at `vanguard\actuarial_checkpoint_{200,400,...,3200}.parquet` (root, not `data\`), 422 KB–13.1 MB, mtimes clustered 2026-05-17 20:10 → 2026-05-18 01:27. Traced to `avshunter_db_update.py:223` (`checkpoint_base = "actuarial_checkpoint"`), written every 200 tickers during a fetch loop; mtimes align exactly with `vanguard/logs/actuarial_full_rebuild_20260517_v2.log`'s finish time. Confidence 90% these are a single run's checkpoints, not a distinct data family.

**`actuarial_cache.parquet`** (299,845 B, 871 rows, 43 cols, state-keyed not date/ticker-keyed) and **`behaviour_cache.parquet`** (38,511 B, 462 rows, 10 cols) — smaller, purpose-built derived caches, not raw-data stores.

## `actuarial_db.sqlite` — two copies, both empty

`AVSHUNTER-Intelligence\data\actuarial_db.sqlite` (0 B, mtime 2026-05-20 21:34:24) and `vanguard\data\actuarial_db.sqlite` (0 B, mtime 2026-05-20 21:37:25, three minutes later). Neither has a valid SQLite header. Neither has ever been tracked in either repo's git history. Both are matched by `*.sqlite` in the respective `.gitignore`. The three-minute mtime gap is suggestive of a shared origin but not proof (confidence 55%).

## `iv_history_cache.db`

`AVSHUNTER-Intelligence\data\cache\iv_history_cache.db`. SQLite 3, WAL mode. **Size observed differently by two independent reads in this investigation**: the pre-established brief stated 471,040 bytes at mtime 2026-07-28 23:13; a later read in this investigation observed 573,440 bytes at mtime 2026-08-03 15:36 (today). The investigating agent's own read-only connection created `-shm`/`-wal` sidecar files (normal SQLite WAL behavior) but assessed this as unlikely to have caused the size/content change itself (confidence 75%); the more likely explanation is that the pipeline genuinely wrote to this cache between the two observations — `options_vol_history` holds rows dated through 2026-07-31, consistent with ongoing writes (confidence 70%). Stated as an open observation, not resolved. Untracked, `*.db`-matched.

## `trade_journal.db` and its archive

`AVSHUNTER-Intelligence\data\journal\trade_journal.db` — 1,581,056 B, 3 tables (`trades`, `closed_trades`, `calibration_reports`), untracked. `AVSHUNTER-Intelligence\data\journal\archive\trade_journal_pre_open_trade_clear_20260511_231243.db` — 262,144 B, same schema shape, a point-in-time snapshot; its birth timestamp (2026-05-11 23:12:43) matches its own filename suffix to the second (confidence 99%).

**Duplicate copies found outside the production path** (not opened/verified, flagged only): `C:\Users\ACKVerissimo\Documents\Codex\2026-05-14\files-mentioned-by-the-user-avshunter\journal_confirmation_extracts\trade_journal_copy.db` and `trade_journal_copy_execute.db`, plus several dated `backups_2026061x_*\trade_journal.db` snapshots — all in what read as ad hoc dev/repair working folders, not the live path.

## `phantom_history.db` and its backup — the two largest stores found anywhere

`AVSHUNTER-Intelligence\data\phantom\phantom_history.db` — **16,085,766,144 bytes (~16.1 GB)**, confirmed genuine SQLite via header + `PRAGMA page_size=4096`/`page_count=3,927,189` cross-check (product matches file size). `PRAGMA freelist_count=0` — none of the size is unreclaimed deleted-page bloat; it reflects live, referenced data (confidence 95%). 10 tables. Untracked, `*.db`-matched.

`...phantom_history.pre_marketdata_update_20260725_065732.bak.db` — 15,138,578,432 B (~947 MB / 6% smaller than live, consistent with ordinary forward growth since the backup, confidence 85%). Birth timestamp matches its own filename suffix to the second.

**Numerous smaller duplicate/test copies found** under `Documents\Codex\...` working folders (a 935 MB `phantom_options_gap_stage.db` tied to a specific July 2026 backfill run — see Part 2 — plus several sub-3MB QA/smoke-test fixtures). Not opened/verified beyond size/name.

## Additional stores found beyond the named candidates

- `AVSHUNTER-Intelligence\config\hybrid_universe_enhanced.csv` (273,748 B) and `config\tickers.csv` / `tickers_ALL_3066.csv` / `tickers_BACKUP_20260128_232859.csv` — static, repeatedly-read universe/ticker lists, not per-run outputs. All untracked, `*.csv`-matched.
- `AVSHUNTER-Intelligence\data\daily\` — 6,567 individual per-ticker CSV files, 74 MB combined — a distributed per-ticker OHLCV cache. Found in the sweep; not traced to writers/consumers in this pass (out of the originally-named scope, flagged for completeness per the task's "find every persistent store" instruction).

---

# PART 2 — Provenance

## `actuarial_database_v6.parquet`

**Every writer found, with `file:line`, and a refinement of the pre-established "two producers" finding:**

| Script | file:line | Tracked? | Role |
|---|---|---|---|
| `add_early_candidate.py` | `:11`, `df.to_parquet(...actuarial_database_v6.parquet)` | Untracked, both repos | **The only script confirmed to write directly to the exact live path by default.** Reads v5, adds one derived column, writes v6. Mtime 2026-05-05, a few hours after v5's creation — this is the file that first created the `v6` name. |
| `avshunter_db_update.py` | `:333` (full merge), `:1012` (`--patch-only`) | Untracked, both repos (and the two repos' copies are **not the same file** — different sizes/MD5s, no git history to arbitrate which is authoritative) | **Updater, but not to the live path by default.** `DEFAULT_OUTPUT` (line 107) is a *different*, staging filename; the live path is only the `--existing` (read) input. Line 1035 prints, but does not execute, `"Promote after review: copy {output} → {existing_path}"`. The one logged invocation found wrote to a third filename, not the live one. Confidence 90% that promotion to the live file is a manual step with no script performing it. |
| `scripts/enrich_actuarial_9dim.py` | `:221`, `df.to_parquet(db_path, index=False)` | **Tracked**, commit `0c40e42`, working tree clean | **In-place column-adder** (`iv_regime`, `horizon_bucket`, `crabel_state`), default `--db` arg is the live path. Not a row producer. |
| `scripts/polygon_actuarial_builder.py` | `:665`, `df.to_parquet(self.output_path, index=False)` | **Tracked**, commit `0c40e42` | **Producer, but default output is the *unversioned* `actuarial_database.parquet`, not v6.** Only writes to the v6 filename with an explicit `--output` override; no log evidence of such an invocation was found. |

This refines, but does not contradict, the pre-established finding: disk evidence (byte-identical rebuild files, matching row counts across the family) supports that both `avshunter_db_update.py`'s and `polygon_actuarial_builder.py`'s output eventually became or fed into the live v6 file — but the mechanism is a manual promotion step outside any script currently in the repo, not a direct write, except for `add_early_candidate.py`'s one-time creation of the name. Confidence 90%.

**A third, previously-undocumented in-place mutator was found**: `scripts/enrich_actuarial_9dim.py` (table above) — its docstring states it backfills `iv_regime`/`horizon_bucket`/`crabel_state` onto rows created before those columns existed in `polygon_actuarial_builder.py`. Both write paths compute the same three columns from the same already-present inputs, so values should be consistent regardless of which wrote them, but this is a second confirmed mutator beyond the two named in prior work.

**Invocation evidence:** Windows Task Scheduler (`schtasks /query /fo LIST /v`, 290 tasks, read-only query) contains **no task referencing "actuarial" anywhere** — the only AVSHUNTER-related scheduled tasks are `AVSHUNTER_MACockpit_*` and `AVSHUNTER_NewsTerminal_*`, neither of which touches the actuarial builders. All actuarial-builder invocations found in logs were manual, via hand-rolled `.cmd` wrappers (`vanguard/logs/run_actuarial_full_rebuild_*.cmd`), clustering on 2026-05-17 09:36–10:12 and 2026-05-18 01:27. One run recorded a Windows-level failure (`"A specified logon session does not exist"`) — an OS/session issue, not a data failure. **The live file's actual last-write timestamp (2026-07-25 07:12:51) has no corresponding log entry anywhere** — what process performed that write could not be determined (confidence: could not determine).

**Overlap — producers can and do write the same rows, and they disagree.** The dedup key `avshunter_db_update.py:1000-1003` uses is the *raw date string*, not the calendar date — so a `"2022-01-27"` row and a `"2022-01-27 04:00:00"` row for the same ticker are never recognized as the same row and never deduplicated against each other. Both sets of rows persist in the live file. See Part 3 for the quantified extent and the confirmed disagreement.

**Mapping the 62/38 date-format split to date ranges (Part 2 task item 5) — not a clean temporal split:**

| Group | Rows | % | Date range | Unique calendar dates |
|---|---|---|---|---|
| FULL_TIMESTAMP (`2021-03-30 04:00:00`-style) | 3,740,896 | 62.01% | 2021-03-30 → 2026-01-29 | 1,215 |
| DATE_ONLY (`2022-01-27`-style) | 2,292,176 | 37.99% | 2022-01-27 → 2026-06-24 | 725 |

652 of the 725 DATE_ONLY calendar dates (90%) also appear in the FULL_TIMESTAMP group's range. **This is interleaved, not temporal** — the DATE_ONLY group is not "the newer half," it is a second, largely-overlapping write of substantially the same ticker/date universe by a different producer. **2,012,453 `(ticker, calendar_date)` pairs — 4,024,906 rows, two-thirds of the entire database — are written twice, once per format-group.** Confidence 100% (direct computation on the full column, after correcting a mixed-format parsing bug caught during the investigation — see Part 3 methodology note).

**Third, earlier producer — found, but assessed as the same lineage evolving, not a genuinely independent codebase (confidence 75% same-lineage / 25% residual uncertainty, not diffed line-by-line):** the earliest `.py` files touching "actuarial"+"database" in either repo, by mtime: `scripts/Archive/actuarial_builderdnu.py` (2026-02-08, class `ActuarialDatabaseBuilder`) and `scripts/Archive/polygon_actuarial_builderdnuold.py` (2026-02-08, class `PolygonActuarialBuilder`, same docstring header as the current tracked file), followed by several more `dnu`/`old`/`updated`-suffixed archive copies through 2026-03-07. These predate the earliest on-disk data file (`actuarial_database.parquet.backup`, 2026-02-19) by ~11 days and predate the tracked builder's git addition (2026-05-20) by over three months. Both early files share exact class names and docstrings with the current tracked scripts — reads as the same builder iterated through archive-suffixed copies, not a separate third producer.

## `actuarial_db.sqlite` (both copies)

**Zero writers found.** Every `actuarial_db`-shaped path constant in the codebase (`ACTUARIAL_DB_PATH` in `intelligent_orchestrator.py:377`, `vanguard/config.py:12`, others) resolves exclusively to `.parquet`, never `.sqlite`. Grepped both repos, all file types, for the literal filename and for `.sqlite` generally — no hits beyond the `.gitignore` pattern itself. Reads as a leftover from an abandoned SQLite-based design or a one-off manual `sqlite3.connect()` experiment that was never followed by schema creation (confidence: could not determine intent; confidence in "no current writer" is 90%).

## `iv_history_cache.db`

**Sole writer module: `scripts/avshunter_universe_scanner.py`**, which is **tracked** (first commit `b22071f`, last commit `49de227`) but currently has **uncommitted local modifications** (`git status` shows `M scripts/avshunter_universe_scanner.py`) — the code that will run next differs from the last committed version. Schema creation `init_iv_cache()` at `:478-501`. Producers: `upsert_iv_records()` (`:718-738`, `INSERT OR REPLACE INTO iv_history`) and `seed_iv_cache_from_phantom()` (`:609-687`, same table, `source='phantom_history'`). Both use `INSERT OR REPLACE` keyed on `(ticker, sample_date)` — **a later write from either path silently and completely overwrites an earlier one, including the `source` label.** Empirically, 100% of the 5,650 current `iv_history` rows show `source='marketdata'`, 0 show `'phantom_history'` — but this alone cannot establish whether the phantom-seed path has *ever* run (it may simply have been overwritten every time). Confidence in "never ran": only ~40%.

## `trade_journal.db`

**Schema owner / primary writer: `avshunter_trade_journal.py`.** `CREATE TABLE trades` `:101`, `closed_trades` `:191`, `calibration_reports` `:272`. Open: `INSERT INTO trades` `:669`. Close (moves a row conceptually from `trades` to `closed_trades`): `INSERT INTO closed_trades` `:874`. `ml_eligible` updater: `:796`. `outcome_capture.py` is an **indirect updater** — it calls `avshunter_trade_journal.log_exit()` rather than issuing its own SQL. `avshunter_exit_engine.py` is confirmed **read-only** (its only `.execute(` call, line 129, is a `SELECT`) — matches the constraint that the exit engine must not write the journal. `confirmation_ingester.py` is read-only, checks for the `ml_eligible` column's existence before querying and degrades gracefully if absent.

**Invocation evidence via the autoincrement sequence — a genuine gap:** `sqlite_sequence` shows trade IDs allocated 1 through 19, but `closed_trades` holds only 8 of those and `trades` (open) holds zero today. **IDs 1, 3, 4, 5, and 11 were allocated but exist in neither table.** Cross-referencing the archive: IDs 4 (`NLY`) and 5 (`JPM`) were still open as of the archive's 2026-05-11 23:12 snapshot and have since vanished from both tables with no formal close record — removed without being closed. IDs 1 and 3 were already gone before that archive was taken; ID 11 disappeared later still. No `DELETE FROM trades` call site was located in any writer checked. Confidence 85% on the observation; the removal mechanism could not be determined.

## `phantom_history.db`

**`chain_snapshots` writers:** tracked `scripts/phantom_database.py` (`CREATE TABLE` `:157`, `INSERT` `:291-295`, last touching commit `e432e67`); untracked `scripts/phantom_greek_rehydrate.py` (`INSERT` `:398` — this script also declares two tables, `greek_rehydration_audit` and `chain_greek_provenance`, that **do not exist** in the live database's actual schema, meaning it has either never completed a run against this file or ran against a different path — could not determine which); untracked `scripts/run_phantom_backfill_parallel.py` (`:216`).

**`options_greeks_history` writers — entirely untracked:** `scripts/options_db_writer.py` (schema owner, `CREATE TABLE` `:27`, `INSERT` `:137`) called from `scripts/phantom_compute_historical_greeks.py` (untracked; docstring: *"Compute missing PHANTOM historical option Greeks from local MarketData EOD rows"* — direct provenance confirmation this table is MarketData-sourced, confidence 90%), with an audit companion `scripts/phantom_computed_greeks_audit.py` (also untracked). **This entire code path producing the single largest table in the entire inventory (~17.76M rows) has zero git history.**

**Invocation evidence, unusually strong because the database records its own run history:** `options_greeks_run_audit` (24 rows) shows 20 runs clustered 2026-05-25 00:34–03:44 (batches up to 500,000 rows each) plus one larger run same day 18:57–21:46 (7,593,269 rows targeted, 7,486,386 OK) — this single day accounts for the large majority of `options_greeks_history`. Three further runs 2026-07-24 20:31–21:56 recorded `db_path` = a *different*, staging file (`Documents\Codex\2026-07-24\a\work\phantom_options_gap_stage.db`, found independently in the Part 1 duplicate sweep, 935 MB, consistent row-volume order of magnitude — confidence 90% these correspond). The backup file's name/birth-time (`...pre_marketdata_update_20260725_065732...`, matching to the second) sits two days after that staging run and — cross-checking the backup's own audit table, which stops at the 2026-05-25 batch and does not contain the three staging-path runs — strongly suggests the staged computation was merged into production around 2026-07-25 06:57, with this backup taken as a safety copy immediately before. Confidence 75% on the merge inference; the merge script itself was not located.

`phantom_run_audit` (24 rows, roughly one entry every 1–5 days from 2026-05-21 through **2026-07-31**, most recent `run_id` `20260731_083130`) — confirms `phantom_engine.py` (tracked) runs as part of the regular evening pipeline, most recently 3 days before this report.

`backfill_audit` (280,150 rows: 254,521 OK / 23,815 NO_DATA / 55 ERROR, spanning 2026-05-21 → 2026-07-24) shows near-continuous `chain_snapshots` backfill activity across roughly two months, not one burst.

---

# PART 3 — Content and coverage

## `actuarial_database_v6.parquet` — full 55-column profile (exact computation, 148s, no sampling required)

**Methodology note, disclosed because it briefly produced a wrong result:** the investigating agent's first parsing pass used `pd.to_datetime(errors="coerce")` on the mixed-format `date` column; pandas 2.3.x infers one format from the first value and does not fall back per-element even with `errors="coerce"`, silently coercing all 2,292,176 date-only rows to `NaT` and initially producing a false "0% overlap, all rows format-exclusive" result. Caught, reproduced in isolation, fixed with `format="mixed"`, and everything depending on it was rerun. Flagged explicitly as exactly the kind of silent-failure risk this report exists to catch.

No column is 100% null. `catalyst_proximity` is 100% populated with a single constant value (`"NONE"`) — non-null but functionally dead. `schema_version`/`bucket_schema_version` are expected single-value metadata columns. Highest null rates: `outcome_max_gain_10d` 1.71% (103,372), `outcome_max_gain_5d` 1.42% (85,858), `outcome_20d_return` 1.16% (70,052) — all outcome/forward-return fields, consistent with tickers too near the data's end date to have a full forward window. Full 55-row dtype/null/distinct table available; representative columns: `vol_regime` (3 distinct, 0% null), `trend_direction` (3, 0%), `rsi` (2,006,260 distinct, 0%), `state_hash` (871 distinct), `__index_level_0__` (6,033,072 distinct = row count, the stray pandas-index column noted in Part 1).

**Date range: 2021-03-30 → 2026-06-24.** Rows per year: 2021: 572,165 (partial, from 03-30) · 2022: 1,452,420 · 2023: 1,447,253 · 2024: 1,392,676 · 2025: 888,671 · 2026: 279,887 (partial, through 06-24).

**Ticker coverage:** 3,616 distinct tickers. Rows per ticker: min 5, median 1,940, max 1,940. 2,074/3,616 (57.4%) have the full 1,940-row history; 1,542 (42.6%) have partial/sparse coverage, sparsest being `SUME` (5 rows), `CORZQ` (6), `NBLX` (9), `MCAP` (18), `CMD` (24), `CNIG` (29), `MFL` (30) — not investigated further for cause (listing/delisting/universe-membership changes are plausible but unconfirmed).

**Duplicates — the significant finding, quantified.** Zero exact `(ticker, literal-date-string)` duplicates. But **2,012,453 `(ticker, calendar_date)` pairs — 4,024,906 rows, 66.7% of the entire database — are written twice, once per date-format producer group.** A random sample of 15 of these overlapping pairs (seed 42), comparing `price`, `vol_regime`, `trend_direction`, `wyckoff_phase`, `outcome_20d_return`, `atr_percentile`, `rsi`, `state_hash`, `macro_regime`: **15/15 pairs disagreed on at least one column.** `atr_percentile` and `rsi` differed in **all 15** (consistent with the pre-established finding that the two producers use different ATR-smoothing and percentile-window conventions — this is that source-level disagreement showing up as concrete row-level numbers). `wyckoff_phase`/`state_hash` differed in 10/15; `vol_regime`/`trend_direction`/`macro_regime` in 4/15; `outcome_20d_return` differed non-trivially in 2/15. One pair showed a >24x price discrepancy (AGL, 2023-02-17: 569.75 vs 22.79) — plausibly an unreconciled stock-split adjustment between the two producers, but not verified against AGL's actual split history (confidence in the discrepancy: 100%; in the explanation: 30%). **This is a significant finding, stated plainly per the task's own instruction: it is not two identical copies under different formatting, it is two independently-computed, differing observations for the same ticker-day, both present and both currently readable by any consumer that doesn't know to deduplicate on calendar date.**

**Internal consistency split by producer group (Part 3.6):**

| `vol_regime` | EXPANSION | NORMAL | COMPRESSION |
|---|---|---|---|
| DATE_ONLY (37.99% of rows) | 45.70% | 37.86% | 16.44% |
| FULL_TIMESTAMP (62.01% of rows) | 41.40% | 38.56% | 20.04% |

| `trend_direction` | SIDEWAYS | DOWN | UP |
|---|---|---|---|
| DATE_ONLY | 47.94% | 27.97% | 24.09% |
| FULL_TIMESTAMP | 49.48% | 25.54% | 24.98% |

(Weighted average of the two groups reproduces the whole-file unconditional figures — 43.04/38.29/18.67 and 48.90/26.46/24.64 — to within 0.01pp, an internal consistency check on the split computation itself.) The two producer-groups' distributions are close but not identical — DATE_ONLY skews ~4pp more toward EXPANSION and ~4pp less toward COMPRESSION — a real but secondary effect next to the row-level value disagreement above.

## `iv_history_cache.db`

`iv_history` (5,650 rows): `ticker` (0% null, 431 distinct), `sample_date` (0% null), `atm_iv` (0% null, plausibility not separately validated), `source` (0% null, currently 1 distinct value: `'marketdata'`). Date range 2025-08-04 → 2026-07-27. No duplicate `(ticker, sample_date)` rows (structurally enforced by primary key). **Rows per ticker: min 1, max 49** — most of the 431-ticker universe has only a single spot sample, a subset has near-full weekly history; a real and confirmed coverage gap. `options_vol_history` (215 rows, 110 distinct tickers) spans only 4 calendar days (2026-07-28 → 2026-07-31).

## `trade_journal.db`

`trades`: 0 rows currently, 127 columns, **notably lacks an `ml_eligible` column** that `closed_trades` has (confirmed by full enumeration) — a schema asymmetry directly relevant to the CLAUDE.md Sprint-4 `ml_eligible` work: an open-then-closed trade has no `ml_eligible` value until it lands in `closed_trades`.

`closed_trades` (14 rows, 121 columns): `ticker` 0% null, 10 distinct (`SOFI`×3, `F`/`DHR`×2, six singles). `entry_date` 2026-03-06→2026-06-24; `exit_date` 2026-04-27→2026-07-18. `options_direction`: 1/14 blank, CALL=5, PUT=8. `outcome_class`: TRUE_WINNER=7, TRUE_LOSER=5, OUTCOME_LOSS=2. `ml_eligible`: 9 rows=1, 5 rows=0 (the 5: blank-direction row, two `LIVE_UAT_SMOKE_FLAT` rows, and two `EXPIRED_WORTHLESS` rows including the PYPL trade referenced elsewhere in this codebase's exit-engine motivation) — broadly consistent with, though not numerically identical to, the "10 real, 3 compromised" framing cited in CLAUDE.md (confidence 90% these describe the same underlying situation). Many `ct_*`/`eil_*`/sector-related columns are **100% null across all 14 rows** (e.g. `ct_bifurcation_proximity`, `sector`, `regime_sensitivity_score`, `expected_value_5d/10d/20d`) — whether these are unpopulated-by-design or a broken write path could not be determined from data alone. `ct_entry_sheet` is present in all 14 rows but with a single constant value `'UNKNOWN'` — non-null but effectively empty.

`calibration_reports` (10 rows): all generated within one week, 2026-06-06 → 2026-06-13. Several accuracy/hit-rate columns 100% null across all 10.

## `phantom_history.db` (sampled — full scans judged disproportionate, method disclosed)

**Row-count methodology, disclosed per the task's cost/speed rule:** a preliminary `SELECT MAX(rowid)` probe on the two large tables took 30.3s and 72.7s respectively — abnormally slow for what should be an indexed lookup (possible disk/volume characteristic, not confirmed, confidence 40% on that specific explanation) — so `MAX(rowid)`/`MIN(rowid)` was used as an **upper-bound proxy** rather than a full `COUNT(*)` scan (valid for ordinary rowid tables; over-counts only if rows were ever deleted). Small tables were counted exactly, near-instantly: `backfill_audit`=280,150, `iv_surface_history`=37,961, `phantom_scores`=34,055, `options_greeks_run_audit`=24, `phantom_run_audit`=24, `mechanism_weights`=0, `phantom_outcomes`=0 (both confirmed genuinely empty, not just fast), `schema_meta`=1 live row (rowid 66 — the row has been rewritten ~66 times via `INSERT OR REPLACE`, consistent with repeated process restarts rather than 66 schema versions).

Content sampled via `ORDER BY rowid ASC/DESC LIMIT 1000` (head+tail, 2,000 rows combined per table) rather than a random or full sample, disclosed as covering the oldest and newest data but missing the middle:

- **`options_greeks_history`**: core fields 0% null in sample; `iv`/`delta`/`gamma`/`theta`/`vega` 0.8% null (16/2000, presumably failed solves). Head-sample date uniformly 2024-05-17; tail uniformly 2026-07-17 — consistent with the backfill window recorded in `options_greeks_run_audit`.
- **`chain_snapshots`**: core chain fields 0% null. Greek columns: **50.5% null in the combined sample, but sharply uneven** — head (oldest, 2021-05-28→2021-09-24) sample is **100% null** on Greeks, tail (newest, 2026-05-22) sample is **0.9% null** with the remainder `'COMPUTED_BS'`. **This directly and consistently matches the backfill window (2024-05-17 onward) found in the run-audit table** — `chain_snapshots` rows older than that, extending back to at least 2021-05-28, remain permanently un-hydrated on Greeks unless a future run extends the window backward. Confidence 90% (three independent data sources agree: run-audit dates, head-sample dates, head-sample null pattern).
- Row-per-ticker distribution was **not computed** for either large table — judged disproportionate given the demonstrated per-query cost; explicitly not run rather than run blind.

Duplicate rows are structurally impossible for the two large tables (composite primary keys enforced at the schema level); near-duplicates were not separately checked given scan cost.

## `phantom_history...bak.db` (backup)

Same schema, ~6% smaller. A second full sampling pass was judged disproportionate (this file's equivalent `MAX(rowid)` queries were even slower — 96.5s and 78.6s — than the live file's, and the schema/population pattern are structurally identical) and was explicitly not run. One real content difference found without a full scan: `iv_surface_history` is 0 rows in the backup vs. 37,961 live — consistent with ordinary forward progress, not divergence (not value-diffed against the live rows, confidence 70%).

---

# PART 4 — External data dependencies

All of Part 4 was established from already-cached local files — parquet metadata, one `date`-column read, SQLite reads, and source/log reads. **Zero live Polygon or MarketData API calls were made or are needed to answer any item below.**

## 4.1 — Provider attribution, per store

**`actuarial_database_v6.parquet` (all 55 columns): 100% Polygon-sourced or locally-derived from Polygon data. Zero MarketData dependency.** Confirmed by reading both builder scripts' complete computation graphs: `avshunter_db_update.py`'s `_polygon_fetch()` (`:868-901`) hits `api.polygon.io/v2/aggs/ticker/.../range/1/day/...`; `polygon_actuarial_builder.py`'s `fetch_daily_bars()` (`:134`) hits the same Polygon endpoint family. There is no MarketData import or URL anywhere in either file. Every derived column (technicals, regime/phase classification, forward-return outcomes, the 9-dim scenario layer including `iv_regime` — see 4.4, it is **not** implied vol despite the name) is computed locally from that Polygon OHLCV. Confidence 100%.

**`iv_history_cache.db`: 100% MarketData-sourced, confirmed via data, not just code.** `SELECT source, COUNT(*) GROUP BY source` on `iv_history` returns a single row, `('marketdata', 5650)`. `options_vol_history` (options volume) is necessarily MarketData, since Polygon carries no options entitlement.

**Options-dependent fields in the live pipeline** (found while investigating, not exhaustively enumerated beyond this): `scripts/avshunter_options_intelligence.py`'s options-scoring layer — `implied_vol`, `delta`, `gamma`, `theta`, `vega`, `open_interest`, `bid/ask/mark`, and MarketData's own `ivRank`/`ivPercentile` fields (the `MD-IV-FIX` block, `:1341-1358`) — all require MarketData's options chain. This is expected/by-design, not a defect; noted only to answer the question asked.

## 4.2 — Rows outside Polygon's 5-year window: **4.17%, 251,437 of 6,033,072 rows**

Assumption stated plainly: "today" = 2026-08-03 (the session date), so the cutoff is **2021-08-03**. Established via a single-column `date` read of the full 6,033,072-row parquet (a few seconds, zero API cost, no sampling needed). Rows strictly before 2021-08-03: **251,437 (4.17%)**. Rows on/after the cutoff: 5,781,635 (95.83%). **Stated plainly per the task's instruction: the overwhelming majority of the database (>95.8%) falls inside Polygon's current reachable window as of today.** Only the earliest ~4 months of 2021 data is already outside it. This is a moving window — more of 2021-2022 will fall out of range as time passes; today's figure is a snapshot, not a fixed line. Confidence 100% on the row counts (direct read); the entitlement's exact "5 years" boundary was taken as given per the task's provider table and was not independently re-verified against a live Polygon call (unnecessary per the task's own guidance, since it was already given as a known fact).

## 4.3 — Columns requiring options data

**None in `actuarial_database_v6.parquet`** — see 4.1, exhaustively traced. Options-dependent fields exist in `iv_history_cache.db` and throughout the live options-scoring layer in `avshunter_options_intelligence.py`, as detailed above.

## 4.4 — `compute_iv_context()`: the reference distribution is **realised volatility, not historical implied volatility** — with one important implementation caveat

**File:** `scripts/avshunter_options_intelligence.py`. Function definition confirmed at line 3161 (prior citation "around 3341-3373" for the primary calc confirmed accurate); historical-closes fetch confirmed at line 2942 (prior citation "around 2942-2960" confirmed accurate).

**Answer, confidence 100% (direct, unambiguous code read):** the reference distribution — what current ATM IV is ranked *against* — is built entirely from **realised volatility computed from historical close prices**. There is no code path anywhere in this function that re-fetches or uses a historical *implied-vol* time series.

Mechanism: `_fetch_hist_closes(ticker, 252)` (`:3270`) returns plain historical closing prices. `rv_series` (`:3341-3347`) is `np.std(returns[i:i+21])*sqrt(252)` computed purely from those closes — a rolling 21-day realised-vol series. The percentile (`:3356-3373`) is a min-max scaled position of the current single live `atm_iv` snapshot against that `rv_series`'s range. **Numerator** = one live options-derived value (one chain fetch). **Denominator basis** = price-derived, in principle free/Polygon-reachable.

**All other code paths in the function** (per the task's request to describe rather than pick one): empty-chain early exit (no distribution built at all); an IV-sourcing fallback chain that only affects how the numerator `atm_iv` is obtained, not how the reference distribution is built; an `atm_iv is None` sentinel path that falls back to a still-realised-vol-based VRP signal, or hardcoded hardcoded defaults (`iv_percentile=0.50`) if that also fails; and a `len(closes) < 60` fallback that abandons the distribution approach entirely for hardcoded absolute IV-level buckets.

**A separate, second "IV percentile"-shaped mechanism exists elsewhere in the same file**, outside `compute_iv_context()`: at `:1341-1358`, per-contract MarketData quote enrichment (called once per selected contract, "1 credit per call" per its own docstring) reads MarketData's own native `ivRank`/`ivPercentile` fields directly, with a comment stating this "replaces the `compute_iv_context()` Polygon-based calculation which fails..." How MarketData computes *its* `ivRank` internally is opaque/server-side and, by definition, would be genuinely historical-IV-based if so — but that's a different mechanism from the one this question asked about, confirmed structurally separate at the function-boundary level (confidence 90%); which of the two ultimately wins if both are present on the same output row was not traced.

**Implementation caveat that matters for the "cheap vs. prohibitive" framing:** although the reference distribution's *underlying data* is price-derived and therefore cheap in principle, `_fetch_hist_closes()` as currently coded (line 2946) calls **MarketData's** stock-candles endpoint, not Polygon's — despite the data itself being exactly the kind of thing Polygon's 5-year OHLCV entitlement already covers for free. This is a MarketData *stocks* endpoint, not an *options* endpoint, so it is very likely not subject to the per-symbol options billing tier — but no in-repo documentation confirms the exact credit cost of this specific endpoint, and no live call was made to check (per the cost-avoidance instruction). **Net: the reference distribution is conceptually cheap/reconstructable-from-Polygon, but the current implementation still routes it through a MarketData call, at an unconfirmed but likely small credit cost.**

## 4.5 — Daily credit consumption estimate (call-site-derived, not measured — no "credit"/"credits used" string found anywhere in a 126 MB orchestrator log spanning 2026-04-26 → 2026-08-02)

**Evening run (Options Intelligence, real run `20260731_083130`, 1,262 tickers processed per its own summary JSON):** chain fetch uses `mode="cached"`, documented in-code as "1 credit per request regardless of chain size" (a comment there records the reason: an earlier incident where per-symbol billing on a 537-ticker run exhausted the daily limit) → ~1,262 credits; historical-closes fetch (4.4) → ~1,262 more; best-contract quote enrichment (1 credit/call, fires per signal) → up to ~1,262 more. **Rough estimate: 2,500–3,800 credits for one evening pass** (confidence 70% — the per-call costs and ticker count are directly observed; the assumption that contract-quote enrichment fires for nearly all 1,262 rows is inferred).

**Morning gate (`morning_gate.py`, same run's `morning_candidates_20260731_083130.csv`, 952 rows):** live-contract quote, 1 call/ticker (up to 3 more on repair-retry). A separate skew-fetch call site (`:664-715`) issues **two** MarketData chain calls per ticker (call side + put side, `strikeLimit=3` each) and — confirmed by reading the code — does **not** use the `mode=cached` protection the evening path uses, so each could bill up to 3 credits under the "billed per symbol returned" options pricing. **Rough estimate: 950–6,600 credits**, wide range because real per-call returned-symbol counts weren't measured (confidence 60%).

**Combined estimate: roughly 3,500–10,400 credits per full evening+morning cycle, against the 100,000/day allocation** — comfortably within budget under this estimate, but explicitly a bounded estimate, not a logged total.

**Same or different 09:30 ET window — investigated empirically rather than assumed, and the answer is inconclusive.** Actual observed run pairs are same-calendar-day (evening output mtime 11:57, morning-gate output mtime 15:21, ~3.4 hours apart — not an overnight evening-to-next-morning gap), and evening-workflow start times across sampled log history are irregular (08:18, 13:44, 21:51, 22:58, 00:34 on different dates, with multi-day gaps between runs) — reading as ad hoc/manual or test-cadence execution rather than a disciplined nightly-then-next-morning schedule. **Timestamps' timezone could not be confirmed** (no explicit TZ marker found in the logging setup examined), so whether a given evening run and its paired morning gate genuinely fall in the same or different 09:30 ET reset window could not be established empirically (confidence: could not determine for actual production timing; confidence 90% on the general logical point that a pre-09:30 evening run and a post-09:30 same-day morning run share one window, while a run occurring after the next day's 09:30 reset would not).

---

# PART 5 — Dependency map

## `actuarial_database_v6.parquet`

**`vanguard/layer2_statistical/actuarial_query.py`'s `ActuarialQueryEngine`** is the load point. `_load_database()` (`:252-306`) silently drops any requested column absent from the file (`query_columns = [col for col in ACTUARIAL_QUERY_COLUMNS if col in available_columns]`, no error) and wraps the whole load in `try/except: self.df = None` — a load failure degrades silently (console `print` only). Construction itself (`__init__`, if the path doesn't exist) **raises `FileNotFoundError`** — fails loudly at that specific point. `.query(state)` **never raises**: `if self.df is None or len(self.df)==0: return _empty_outcomes()`, and both `_find_similar_states`/`_calculate_outcomes` are individually try/excepted back to the same empty-result fallback — a `KeyError` on a silently-dropped column degrades to empty outcomes rather than crashing.

**`vanguard/main.py`'s `VanguardEngine`** — the real live consumer. `__init__` **raises loudly** on missing file, wrong filename, or (via `_validate_actuarial_database_contract`) any *required* column missing; **only prints a warning** (graceful, logged degrade) for missing *optional* columns, disabling `early_candidate` logic in that case. **Sole live caller: `scripts/run_vanguard_from_packages.py:1374`**, at module scope, **not** wrapped in try/except — a missing/invalid store crashes the whole script before any ticker processes. Per-ticker `.analyze()` calls (`:1472/1475`) *are* individually try/excepted, so a single-ticker failure degrades gracefully once construction has succeeded. This script runs as orchestrator Phase 6 (`RUN_VANGUARD`, `intelligent_orchestrator.py:343`) with **`critical=True`** — a failure here aborts the entire evening run. **Net: a fully-missing/corrupt store fails loudly and halts the pipeline; silently-dropped optional columns degrade gracefully and the pipeline continues on reduced fidelity.**

**`avshunter_ticker_probe.py` — a currently-broken import path, silently masked.** Line 140 imports `vanguard.pipeline.VanguardPipeline`, which **does not exist anywhere in the repo**; line 148 imports `vanguard.layers.actuarial_query.ActuarialQueryEngine`, from a directory (`vanguard/layers/`) that **also does not exist** (only `vanguard/layer2_statistical/` does). Both caught by `except ImportError`, both set the relevant class to `None`. Even if the import somehow succeeded, the script calls `.query_by_state(state_dict)` (`:527`) — a method the real class doesn't have (only `.query(state)`). **Net effect: this script's actuarial-database code paths are always unreachable**, and it silently falls through to a `STANDALONE_FALLBACK` that infers a verdict from Wyckoff phase and regime alone, **never touching the actuarial database at all**, while producing output structurally similar to a real actuarial-backed verdict. A "Degraded mode" warning prints to console but the script never errors. Confidence 90% this is a live, currently-reachable bug (grep-confirmed both missing paths and the method mismatch).

**`scripts/actuarial_enrichment_pass.py`** — correction to a prior framing: it does **not** read `actuarial_database_v6.parquet` directly; it reads `actuarial_cache.parquet` (a derivative) via `actuarial_cache_builder.load_cache()`, plus `behaviour_cache.parquet`. Runs as Phase 8.5. Every failure mode found (cache load, per-ticker lookup, missing `behaviour_state_hash` column) degrades gracefully — logged, never raised, run continues with a tallied failure counter.

## `actuarial_db.sqlite` (both copies)

**Zero consumers found**, matching Part 2's zero-writers finding — a literal-string grep across both repos, all file types, returns nothing.

## `iv_history_cache.db`

**Sole consumer/owner: `scripts/avshunter_universe_scanner.py`.** `get_cached_iv_series()` degrades silently to an empty `pd.Series` on zero rows. `compute_vms()` falls back to a synthetic realised-vol-based proxy (`iv_rank_source="SYNTHETIC"`, confidence 0.65 vs. 0.95 for real data) when fewer than 10 real observations exist for a ticker — this numeric confidence value **feeds directly into the GO/PROBE/WAIT/BLOCK decision**, a genuine branch, not passthrough. Missing MarketData key short-circuits to an empty series before the DB is even touched. **Not registered as a live orchestrator phase** — the orchestrator only checks the script exists and passively reads a manifest file it produces if fresh; the scanner itself must be run manually.

**A related, likely-dead adjacent mechanism found:** `avshunter_options_intelligence.py`'s own `_load_iv_history()` reads a *different*, JSON-based per-run mechanism (`iv_history.json`), architecturally unrelated to this SQLite store — and **no writer of that JSON file was found anywhere in the repo**, meaning `classify_iv_regime()` downstream likely always degrades to `'UNKNOWN'` in production (confidence ~85% this path is effectively dead).

## `trade_journal.db`

Three modules bypass the module's own API with direct `sqlite3.connect()`: **`avshunter_exit_engine.py`** — fully graceful (`if not db_path.exists(): return []`, broad `except: return []`), with an explicit `DATA_UNAVAILABLE` guard when current premium is missing/non-positive — never fabricates a verdict on stale data; confirmed **wired into the live morning run** (`morning_thesis_validator.py:2943-2952`, non-critical try/except). **`confirmation_ingester.py`** — checks for the `ml_eligible` column's existence before querying, returns `None` gracefully if absent or the file is missing; gated at `MIN_ELIGIBLE_TRADES=30` (currently only 9/14 closed trades qualify, so the regression this feeds is currently always skipped in practice); **not called from any live pipeline phase**. **`scripts/qa_live_uat_readiness.py`** — the one consumer of this store that **fails loudly** (a severity-1 flag) if the file is entirely absent; a standalone QA tool, not orchestrator-wired.

`avshunter_trade_journal.py` itself degrades silently on read (`except: return set()`/`[]`) but raises `ValueError` loudly on `log_exit()` for an unknown `trade_id` (a write-path, human/Lab-UI-triggered guard). `outcome_capture.py` and `weekly_intelligence_report.py` are confirmed-live consumers via the proper module API, both non-critical try/except in the orchestrator. `intelligence_lab.py` (standalone dashboard) is a hybrid — uses the module's connection factory but then issues its own raw `UPDATE` statements for Lab-specific columns, silently swallowing failures via bare `print`, and exposes an `/api/log_exit` HTTP endpoint writing outside the CLI-only path the exit-engine design otherwise assumes.

## `phantom_history.db`

**Live call site is inline inside `evening_workflow()`** ("PHASE 7.5: PHANTOM SCORING ENGINE", `intelligent_orchestrator.py:3824-3899`), which subprocess-invokes `phantom_engine.py`. **A separate, fully-built `run_phantom_layer()` function (`:2149-2180`) is dead code — never called anywhere**, confirmed by full-file grep. The live path is **fully fail-open, quoted verbatim**: a non-zero exit is caught and logged ("Continuing with original OI CSV"); a missing input CSV logs "Phantom skipped"; any exception including a 1200s timeout is caught and logged as a warning — **no pipeline abort under any Phantom-DB failure mode.** Inside `phantom_engine.py` itself there is no try/except around the DB calls, so a real sqlite error propagates uncaught up to the orchestrator's fail-open subprocess boundary, where it's caught. `apply_payload()` genuinely branches: it overwrites `options_score` and sets `options_route_verdict` for EXECUTE/ARMED promotions — a real effect, though `execution_permission` is deliberately left untouched (advisory-only by design). Missing-history degrades inside the scoring mechanisms are silent (zeroed/neutral fallback values, no exception).

**EIL (`execution_intelligence.py`) does not reference "phantom" by name anywhere** (zero grep hits) but can transitively receive a phantom-adjusted `options_score` via CSV lineage; EIL's primary gate field (`sb_final_verdict`) maps from `options_verdict`, which Phantom does not overwrite — so EIL's headline gate is phantom-blind even though a phantom-touched score may ride along unused (not verified further, out of scope to trace EIL's internals here).

**`avshunter_universe_scanner.py`** also reads this store read-only/immutable to seed `iv_history_cache.db` (cross-referenced above) — same silent `except sqlite3.Error` degrade pattern.

## Lower-priority stores

`actuarial_checkpoint_*.parquet`: write-only debris, **zero consumers found** anywhere — no resume/read-back logic exists. `actuarial_cache.parquet`: producer `actuarial_cache_builder.py`, live-wired as orchestrator Phase 4.6, consumed by `actuarial_enrichment_pass.py` (above) plus a non-fatal post-build existence check; two standalone manual diagnostics (`check_cache.py`, `regime_audit.py`) have unhandled `FileNotFoundError`s if it's absent. `behaviour_cache.parquet`: single producer/single consumer pair, both already covered above. The task brief's reference to `early_candidate.parquet` as a named store is very likely (confidence 85%) a conflation with the `early_candidate` *column* inside `actuarial_database_v6.parquet` — that column does have several live consumers, all `getattr(..., default)`-guarded, none hard-failing on absence.

## Cross-cutting observation

The dominant failure-mode pattern across every store examined is **silent degradation with a breadcrumb** — a console print, a log line, a tallied counter, or a marker file — not silent-with-zero-trace. But none of these breadcrumbs are asserted against or gated on anywhere; a human has to actively watch stdout/logs to notice. Exactly two consumers found anywhere in this investigation **fail loudly**: `VanguardEngine`'s construction against the live actuarial parquet (halts the entire evening run), and `qa_live_uat_readiness.py`'s missing-journal check (a standalone QA tool). Everything else degrades gracefully or silently, whether by design or by accident.

---

# PART 6 — Observed gaps

A factual list, no recommendations. Confidence stated per item.

1. **Two persistent stores are entirely empty and orphaned.** Both copies of `actuarial_db.sqlite` (repo root and `vanguard/data/`) are 0-byte files with no valid SQLite header, no git history ever, and — confirmed independently by two separate investigations — zero identified writers or readers anywhere in either codebase. Confidence 90%.
2. **Vocabulary/schema mismatch: the same physical database was written by (at least) two independent, disagreeing calculation conventions.** The `date` column's 62%/38% format split maps to two producers whose outputs interleave rather than partition temporally, and 66.7% of all rows exist as a duplicated `(ticker, calendar_date)` pair where the two copies disagree on substantive computed values (`atr_percentile`/`rsi` differ in 15/15 sampled pairs; `wyckoff_phase`/`state_hash` in 10/15). Confidence 100% on the duplication/disagreement facts; confidence 75% that this stems from exactly two distinct producer lineages rather than more.
3. **Columns present in the schema but never populated (as distinct from null):** `catalyst_proximity` in `actuarial_database_v6.parquet` (100% populated with the single constant `"NONE"`); `ct_entry_sheet` in `trade_journal.db`'s `closed_trades` (100% populated with the single constant `'UNKNOWN'`); `mechanism_weights` and `phantom_outcomes` tables in `phantom_history.db` (real `CREATE TABLE` definitions, zero rows ever inserted). Confidence 100% (direct counts) on all four.
4. **The single largest table in the entire inventory has zero git history.** The code path producing `phantom_history.db`'s `options_greeks_history` (~17.76M rows, MarketData-sourced) — `scripts/options_db_writer.py`, `scripts/phantom_compute_historical_greeks.py`, `scripts/phantom_computed_greeks_audit.py` — is entirely untracked, as are `phantom_greek_rehydrate.py`, `run_phantom_backfill.py`/`_parallel.py`, and several other Phantom maintenance scripts. Only `phantom_database.py` and `phantom_engine.py` are tracked. Confidence 100%.
5. **Stores/writers that are untracked:** essentially every persistent data file found in this inventory (both `.gitignore`s exclude `*.parquet`/`*.db`/`*.sqlite` blanket-wide), plus a substantial fraction of the *code* that writes to `phantom_history.db` (item 4) and both copies of `avshunter_db_update.py` (which are furthermore **not the same file** between the two repos — different sizes, different MD5s, no git history in either to arbitrate which is authoritative). Confidence 100%.
6. **A writer with genuinely uncertain default behavior relative to its own documented purpose:** neither `avshunter_db_update.py` nor `polygon_actuarial_builder.py` writes to the live `actuarial_database_v6.parquet` path by default — both default to staging/unversioned filenames, and promotion to the live path appears to be a manual step with no corresponding script found in either repo. Confidence 90%.
7. **A currently-broken import path silently produces plausible-looking but actuarially-unbacked output.** `avshunter_ticker_probe.py` imports two module paths that do not exist and calls a method the real `ActuarialQueryEngine` class doesn't have; all three failures are individually caught, and the script always falls through to a non-actuarial standalone fallback while printing (not raising) a degraded-mode warning. Confidence 90%.
8. **A likely-dead JSON-based IV-history mechanism sits alongside the live SQLite-based one**, architecturally unrelated, with no identified writer for the JSON file it expects — its downstream consumer (`classify_iv_regime()`) likely always resolves to `'UNKNOWN'` in production. Confidence ~85%.
9. **Two accounting gaps in `trade_journal.db`'s autoincrement sequence** (trade IDs 1, 3, 4, 5, 11 allocated but present in neither `trades` nor `closed_trades`; IDs 4 and 5 confirmed via the archive to have been open positions removed without a formal close record) with no `DELETE` call site located in any writer checked. Confidence 85% on the observation; the mechanism could not be determined.
10. **A schema asymmetry directly relevant to previously-documented Sprint-4 `ml_eligible` work:** `trade_journal.db`'s `trades` (open) table has no `ml_eligible` column at all; only `closed_trades` does. Confidence 100%.
11. **Date ranges present in one store but structurally absent in a related one:** `phantom_history.db`'s `chain_snapshots` Greek columns are 100% null for all sampled rows before 2024-05-17 (data itself extends back to at least 2021-05-28) — the computed-Greeks backfill was scoped to start there and nothing has since extended it backward. Confidence 90%.
12. **A live pipeline phase (Options Intelligence) currently draws a Polygon-reachable, price-only computation (the realised-vol reference distribution inside `compute_iv_context()`) through a MarketData API call instead**, at an unconfirmed but likely small credit cost. Confidence 100% on the code path; confidence on the credit-cost magnitude: could not determine.
13. **A tracked writer script currently has uncommitted local modifications** (`scripts/avshunter_universe_scanner.py`, the sole writer of `iv_history_cache.db`) — the code that will run next differs from the last committed version. Confidence 100%.
14. **`iv_history_cache.db`'s size/content changed between two observations taken during this investigation** (471,040 B at one prior snapshot vs. 573,440 B moments before this report), with the cause not fully resolved — most likely explained by genuine ongoing pipeline writes rather than the investigating read itself, but not confirmed either way. Confidence 70% on the "genuine writes" explanation.
15. **Several stores' backup/archive/copy mechanisms could not be traced to any script in either repo**: `trade_journal.db`'s archive snapshot, `phantom_history.db`'s `...pre_marketdata_update...` backup, and the live actuarial parquet's own last-write event (2026-07-25 07:12:51) all have no corresponding log entry, scheduled task, or source file performing the copy/write. Confidence: could not determine, stated plainly for each.
16. **Numerous duplicate/snapshot copies of `trade_journal.db` and `phantom_history.db`** exist under ad hoc-looking dev/QA/repair working folders outside the production data directories (`Documents\Codex\...`). Enumerated by path in Parts 1/2/3 above; not opened or content-verified.
17. **Additional persistent stores exist beyond the originally-named candidates**, found via the mandated broad sweep: static ticker/universe CSVs (`config/hybrid_universe_enhanced.csv`, three `tickers*.csv` variants) and a 6,567-file, 74 MB per-ticker daily-OHLCV CSV cache (`data/daily/`) — both untracked, both `.gitignore`-matched. Not traced to writers/consumers in the same depth as the named stores (flagged for completeness, not investigated further, given the scope already covered).
18. **What I could not determine, consolidated:** the process that performed the live actuarial parquet's last write; whether the two early-2026 `.py` files sharing class names with the current tracked builders are the same lineage or a genuinely independent third producer (assessed 75% same-lineage, not diffed line-by-line); the cause of the one >24x price discrepancy found in a sampled duplicate pair (AGL, 2023-02-17); whether `seed_iv_cache_from_phantom()` has ever actually executed against production data (its writes are indistinguishable from being overwritten by the MarketData-direct path); the exact credit cost of the MarketData stock-candles endpoint used inside `compute_iv_context()`; and whether a given evening run and its paired morning gate fall inside the same or a different 09:30 ET MarketData credit window in actual production operation (timestamps' timezone could not be confirmed from the logging setup examined).

---

## Methodology and scope notes

This report was assembled from four parallel, independent read-only investigations (the actuarial parquet family; all other identified stores; external provider dependencies; and the full consumer/dependency map), each disclosing its own methodology inline above. No live Polygon or MarketData API call was made anywhere in producing this report — every finding came from local files (parquet metadata and data, SQLite databases opened read-only, `.gitignore`/`git log`/`git status`/`git ls-files`, Windows Task Scheduler read-only queries, and source/log files already on disk). No credential value is reproduced anywhere in this document, though the existence of at least one hardcoded-fallback API key pattern was incidentally re-confirmed in a file already covered by prior, separate remediation work.

Per the task's scope discipline: this report records what is, not what should be. No fix, migration, cleanup, or recommendation of any kind was performed or is implied by any finding above. `git status` is clean apart from this report file.
