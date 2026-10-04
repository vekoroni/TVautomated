# Phantom weekly maintenance — 2026-10-02

Scope: only the completed-Friday sessions 2026-09-18 and 2026-09-25. The 2026-10-02 US session was not complete. No Evening or Morning pipeline run was launched and no pipeline code was changed.

## Preflight and rollback

- No Phantom maintenance/backfill/Greek writer was active. The Intelligence Lab was open; maintenance used SQLite WAL and one writer at a time.
- The cleaned `data/universe/polygon_liquid_universe.csv` panel has 3,318 valid tickers. `NAN` and `SYM` are invalid roster text and were excluded from provider requests.
- Created SQLite online backups before writes: `data/phantom/backups/phantom_history.pre_maintenance_20261002.db` (38,857,895,936 bytes) and `data/cache/iv_history_cache.pre_maintenance_20261002.db` (17,641,472 bytes). Do not restore them over active readers or writers.
- Provider fetches used only absent ticker/session pairs, six workers, and a 3,000-credit cap per date. Existing candidate-chain pairs were not requested or overwritten.

## Ingest and derivation

| Session | New OK tickers | New NO_DATA | Provider errors | New chain rows | Estimated credits | Valid panel reconciliation |
|---|---:|---:|---:|---:|---:|---|
| 2026-09-18 | 1,449 | 509 | 0 | 59,436 | 1,960 | 2,809 with chains + 509 NO_DATA = 3,318 |
| 2026-09-25 | 1,398 | 474 | 0 | 70,798 | 1,874 | 2,844 with chains + 474 NO_DATA = 3,318 |

`scripts/phantom_compute_historical_greeks.py` processed only newly fetched ticker/date rows, filling nulls rather than overwriting prior Greeks. It used a 4.5% risk-free input as a model assumption; that value was not verified as the exact historical rate for these dates.

| Session | New rows processed | Five-Greek successes | Explicit solver/input failures | Total valid-panel five-Greek coverage |
|---|---:|---:|---:|---:|
| 2026-09-18 | 59,436 | 58,778 | 658 | 449,806 / 450,464 = 99.8539% |
| 2026-09-25 | 70,798 | 70,006 | 792 | 499,006 / 499,798 = 99.8415% |

The 1,450 failed rows retain quality states such as missing input, invalid price, or no-arbitrage/solver-range violation; no numeric Greek was fabricated for them.

`derive_iv_history` filled only ticker/date pairs lacking an IV surface, preserving existing candidate surfaces. On 2026-09-18 it derived 1,449 ticker surfaces and 1,433 valid ATM IV cache values; on 2026-09-25 it derived 1,400 ticker surfaces and 1,381 valid cache values. Final `iv_surface_history` rows are 10,522 / 13,839, with 2,812 / 2,844 distinct tickers respectively; the 18 September surface includes three tickers outside the cleaned panel. Final IV-cache ticker counts are 2,799 / 2,825. An IV surface record can exist without a valid ATM IV; this is a quality limitation, not a filled cache value.

## Verification

- Exact duplicate contract count across the valid panel: **0** for each session; `chain_snapshots` also has a unique `(ticker, quote_date, option_symbol)` primary key.
- Both provider batches had zero errors and zero unresolved valid-panel tickers.
- Full live SQLite `PRAGMA quick_check(1)`: **PASS (`ok`)** after 2,929.1 seconds. Journal mode remained WAL. This verifies structural integrity, not the economic usefulness or completeness of every historical observation.
- Older historical gaps and predictive value were not evaluated by this weekly maintenance.
