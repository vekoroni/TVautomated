# AVS-MON-004 — future provenance, horizon coverage and batch canary

**Assessment date:** 22 September 2026. **Activation decision: keep routine outcome capture OFF.** All live control-plane, price and Phantom accesses in this assessment were read-only. No provider API or broker tool was called. Only disposable SQLite stores received outcome writes; they were removed automatically.

## What is implemented now

- `tools/avs_mon004_projection_reconciliation.py` checks complete canonical OPTION_CHAIN registrations against projection outbox state, Phantom receipt hash, receipt row count and immutable revision count. It is an aggregate health check; the governed outcome reader separately verifies exact-row hashes and timestamps at use.
- `tools/avs_mon004_horizon_coverage.py` distinguishes a missing ticker chain, a contract absent from an existing chain, an unversioned raw snapshot and a canonical revision/registered observation across the first five later underlying sessions. It does not turn raw or absent rows into labels.
- `tools/avs_mon004_batch_canary.py` copies a bounded, balanced CALL/PUT family set and its dependencies into temporary control/price stores. It runs a split 100-family capture and a full replay, then checks reconciliation, idempotency, source and label counts, foreign keys, latency, database growth and WAL growth. It cannot change the live decision or outcome stores.
- Permanent classification/selection tests were added. The adjacent ten-suite regression passed **109/109**; the new focused tests passed **10/10**. Existing production capture flag and model activation were not changed.

## Future-data provenance: existing normal route works

The Evening Options stage already registers complete MarketData chains, enqueues a Phantom projection event and delivers that event. Read-only reconciliation of the latest five captured option sessions found **6,753/6,753** complete datasets with matching outbox completion, receipt hash and revision count: 1,316 on 14 Sep; 1,339 on 16 Sep; 1,361 on 17 Sep; 1,363 on 18 Sep; and 1,374 on 21 Sep. This does not independently rehash all 6,753 payload files or every row; the outcome reader verifies a row's immutable hash, registry, receipt, provider and point-in-time availability when it is used.

The separate historical direct-backfill writer is **not** this route. It writes mutable `chain_snapshots` and query-level audit rows without immutable per-contract source evidence. Those rows remain research-only. No new canonical writer was inserted into the normal Evening pipeline because its existing route already reconciles; doing so would duplicate data and risk a working acquisition path.

## 100-family isolated operational canary

The canary sampled 50 CALL and 50 PUT families, containing 840 real assessments. The first 50-family pass scanned 50 in 65.254 seconds and appended 804 labels. The second scanned the remaining 50 in 143.687 seconds and appended 876. A 100-family replay took 76.162 seconds and appended **zero** labels. There were zero reader exceptions, zero foreign-key errors, zero provider calls, and the population reconciled. The temporary store held 2,890 verified source rows and 1,680 hypothetical labels. Control-plane growth was 11,948,032 bytes; measured temporary WAL reached 102,592,152 bytes before checkpoint.

The 1,680 labels are **not 1,680 executable outcomes**. At one session: 792 `COMPLETE`, 42 `COMPLETE_OPTION_PATH_PARTIAL`, 6 `COMPLETE_OPTION_RETURN_UNAVAILABLE`. At five sessions: all **840** were `COMPLETE_OPTION_PATH_PARTIAL`. Ten- and twenty-session horizons had not matured in this sample. The scheduler's `coverage_final` includes partial labels; it must not be interpreted as complete exact-contract coverage.

This is one configured 100-family batch, not a random sample or a full 12,337-family production sweep. At a limit of 100, the current population requires at least 124 scans per cycle. Measured initial capture time for this batch was about 209 seconds, before a repeat. Extrapolation to every family is uncertain, but the current scan strategy and WAL footprint need an explicit operating budget before routine activation.

## Why the five-session path is partial

A read-only census of the same 840 mature assessments covered 14, 15, 16, 17 and 18 September. On **15 September**, no canonical option-chain dataset exists for this cohort: 289 cells have only an unversioned Phantom snapshot and 551 have no exact quote. That single absent session makes a complete governed five-session path impossible for every assessment in this sample.

On **18 September**, 312 exact-contract cells have no quote. Of those, 90 lack a canonical ticker chain, while **222 are absent from an existing ticker chain**. No sampled cell was after its contract's expiry. This proves two different coverage problems: a missed session-wide acquisition and a monitored exact contract dropping out even when its ticker was acquired. The latter may arise from acquisition scope, filters or provider omission; this audit does not assign a cause without the source request/response evidence.

## Remaining changes and activation gates

1. **Preserve daily session continuity.** Reconcile every completed market session against the expected canonical option-chain capture panel and alert on missing days. Historical 15 September raw snapshots cannot be laundered into canonical evidence; only an independently archived immutable payload or newly acquired, correctly availability-stamped historical observation could fill that research path.
2. **Retain monitored exact contracts.** Before broad-chain selection/filtering, maintain a bounded exact-symbol follow-up worklist for open 1–20-session theses and their contract alternatives. Capture a provider quote or a documented `NO_DATA` for each expected symbol/session, with immutable payload identity and acquisition time. Do not infer a price from nearby strikes or last trade. First determine whether the 222 missing cells were outside request scope or absent in the provider response.
3. **Make coverage meaningful.** Report complete two-sided paths separately from partial terminal labels, by CALL/PUT, horizon, source and missing reason. Re-run time-separated 10- and 20-session assessments when they mature; do not use the current partial five-session labels as long-horizon training targets.
4. **Bound operational cost.** Define an acceptable nightly latency/WAL budget, use due/changed-evidence prioritisation rather than a blind full-population sweep, and validate the revised scheduler on another isolated batch. Prepare a date-scoped rollback/space preflight before any live writer trial.
5. **Keep authority isolated.** Outcome capture remains off, models remain unactivated, and hypothetical labels have no trading, execution or capital authority until the above gates and a controlled live acceptance run pass.

These findings do not invalidate the present Evening or Morning trade thesis outputs. They do show that routine outcome learning for the full 1–20-session horizon is not yet production-ready.

## Reproduce without production writes

From the repository root:

- `C:\Python314\python.exe -m tools.avs_mon004_projection_reconciliation`
- `C:\Python314\python.exe -m tools.avs_mon004_horizon_coverage`
- `C:\Python314\python.exe -m tools.avs_mon004_batch_canary`
