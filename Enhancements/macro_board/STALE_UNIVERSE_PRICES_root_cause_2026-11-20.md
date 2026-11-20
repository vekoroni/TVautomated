# Stale universe ETF prices: root cause and fix options (for ACK's approval)

Date: 20 Nov 2026. Status: **ROOT CAUSE FOUND, FIX NOT BUILT.** Nothing was edited, refreshed, backfilled or run. The price store was read only (`mode=ro`).
Intended location: `Enhancements/macro_board/STALE_UNIVERSE_PRICES_root_cause_2026-11-20.md` in the main checkout. The side session's worktree hook blocked writing there, so this copy sits in the shared notes folder.
Scope: the 39 ETFs in the board universe (`macro_board/config/macro_board_config_v1.json` `universe`) whose last bar in `data/canonical/historical_prices.sqlite` `ohlcv_daily` is 15 May 2026 (37) or 20 Aug 2026 (RSP, UUP).
Raised by: AVS-MACRO-TRIAGE-001 T7, design doc lines 331 and 355.

## 1. Summary

- **The pipeline never fetches these 39 ETFs.** It hasn't since 16 May (the 37) and has never done so since the price store was created on 22 Aug (RSP, UUP). Their store history comes only from the one-time CDS-2 migration on 22 Aug 2026.
  - **15 May (37 ETFs):** they were in the old 1,998-ticker Discovery universe. That universe was replaced on 16 May by the 3,320-ticker stock universe, which holds none of them. The last fetch was the 15 May evening run.
  - **20 Aug (RSP, UUP):** these two were never in the Discovery universe. On 21 Aug the macro-enrichment review lane appended them to Discovery once, so packages were built with history up to 20 Aug. The 22 Aug migration imported those packages. Since then the review lane writes macro-only tickers to an advisory file and never fetches them.
- **The board's own fill already closes the gap on live builds.** On the 19 Nov 23:42 UTC evening build, all 39 were FRESH (last session 19 Nov), filled from the board's grouped-daily cache. The 39 STALE read came from the **`--as-of 2026-11-19` rebuilds used for T7 acceptance**. The fill never runs on an as-of build (`macro_board/build_board.py:208`).
- **The live fill is not safe to rely on as it stands.** Three problems:
  1. It works only because the cache was started on 10 Oct, before the gap passed 120 sessions. If the cache is lost, the gap (130 sessions) is refused for good.
  2. The 37 have only 193 sessions of history on the board, against 1,318 for SPY.
  3. Cached bars are never re-adjusted for later splits. **This is causing a false read now:** BITO's 19 Nov close is 1.98x its 18 Nov close, and the live board shows BITO +98.3% on the day, realised vol 251% and "at its 252-session high". This fits a 1-for-2 reverse split; I have not checked it against a splits feed.

## 2. Evidence: what the store holds

The store was read only, 20 Nov 2026:

| Tickers | Stored range | Rows | Only source in the store |
|---|---|---|---|
| The 37 (IJR, SCHD, XME, ITB, BND, EMB, IAU, GDXJ, UCO, KWEB, MCHI, INDA, EWY, EWT, EWC, EWA, BITO, GBTC, SPXL, SPXU, SOXL, SOXS, TNA, TZA, LABU, LABD, FAS, FAZ, NUGT, DUST, ERX, ERY, BOIL, KOLD, UDOW, SDOW, SDS) | 2026-02-17 to 2026-05-15 | 63 each | `MIGRATION_DAILY_CACHE`, run `20260821_090928` (imported 2026-08-22 16:3x UTC), re-validated by run `20260824_100301_CDS2_EXIT` (0 inserted, 63 unchanged) |
| RSP, UUP | 2021-08-23 to 2026-08-20 | 1,254 each | `MIGRATION_PACKAGE`, run `20260821_090928` (batches `5dc80c68…` RSP and `13befc9f…` UUP, 2026-08-22 16:27–16:29 UTC) |
| SPY, XLK (for comparison) | 2021-08-23 to 2026-11-19 | 1,318 | migration plus `POLYGON_DATA_FETCHER` from 2026-08-24, written by every evening run |

- `price_schema_metadata`: the store schema `cds_historical_prices_v1` was created at 2026-08-22T16:23:40Z.
- The import report `data/canonical/reports/cds2_import_20260821_090928.json` shows 3,615 `data/daily/*.csv` files and 1,616 packages imported, with the last date 2026-08-20.
- Writers of `ohlcv_daily` since then, by `source_kind`:
  - `POLYGON_DATA_FETCHER`: Discovery and `polygon_data_fetcher.py:187` / `avshunter_discovery_ULTIMATE.py:1061`, 3,023 tickers. It never wrote any of the 39.
  - `PACKAGE_BACKFILL`: 190 tickers, 24 Aug–26 Sep.
  - `GROUPED_DAILY_BACKFILL`: 7 Oct, 1,241 tickers.
  - `APPROVED_SAVED_RESPONSE_CATCHUP`: 9 Nov.
  - None of these four wrote any of the 39.

## 3. Root cause, 15 May (the 37)

1. Discovery fetches the tickers in `data/universe/polygon_liquid_universe.csv` (`intelligent_orchestrator.py:461` `UNIVERSE_FILE`, passed as `--universe` at `:1988`), plus the scanner tickers it injects on that run.
2. **Old universe.** `data/universe/Archive/polygon_liquid_universe1605.csv` (1,998 rows, file dated 6 May) contains **all 37**. The earlier `polygon_liquid_universe old.csv` (24 Apr) contains 35 of them.
3. **New universe, 16 May.** It is the 3,320-row sector-tagged stock universe. Its first copy is `Archive/polygon_liquid_universe1705old.csv`, 16 May 14:52 BST, 3,320 rows. It contains **none** of the 39, and neither do the current `polygon_liquid_universe.csv` (git `c808b45` of 20 Aug through `f368d47` of 25 Sep, unchanged at 3,321 lines) or `config/tickers.csv`. The universe files were not in git before 20 Aug, so file timestamps are the evidence for 16 May.
4. **Last fetch.** `data/daily/IJR.csv` was last written 2026-05-15 23:56 BST and `SOXL.csv` 23:58 BST: the 15 May evening run. The last row is 2026-05-15. Those CSVs held a rolling ~63-session cache (17 Feb–15 May), so the migration brought in only 63 rows.
5. **Why later repairs missed them.** The 7 Oct history backfill `Enhancements/phase0/p0_backfill_daily_history.py:10` was scoped to "tickers whose first stored bar is on or after 2026-05-01". The 37 start on 17 Feb, so they were out of scope even though its on-disk source holds them.

**Root cause:** a universe change on 16 May. The board's ETF universe was never registered with any job that writes the store, so nothing noticed when the pipeline stopped fetching these ETFs. There was no provider error and no gap-limit refusal.

## 4. Root cause, 20 Aug (RSP, UUP)

1. RSP and UUP were in none of the Discovery universe files: not the old 1,998 list, not the current one.
2. **How they got history.** On run `20260821_090928` (21 Aug morning) both appear in `discovery_candidates_ultimate_20260821_090928.csv` with:
   - `external_intel_source = MACRO_ENRICHMENT`
   - `external_intel_stage_status = APPENDED_FOR_REVIEW`
   - `external_intel_reason = "Ticker present in macro enrichment exposure index"`

   The review lane appended them to Discovery that day, so Vanguard built packages carrying 5 years of bars up to 20 Aug. The 22 Aug migration imported those packages. Archive: `data/output/runs_compressed/20260821_090928.zip`, packages not kept.
3. **Why it stopped.**
   - The package import was a one-time migration.
   - The review lane now writes macro-only tickers to a separate advisory file. `scripts/apply_external_intel_review_lane.py:7-9` says they "cannot be appended to the core CSV, create Packages/Vanguard work". Status at `:307` is `ADVISORY_ONLY_NOT_DISCOVERY`. This is the `667620e` 4 Sep baseline, against `APPENDED_FOR_REVIEW` at `ea0adb9` on 5 Aug.
   - On 19 Nov RSP appears only in `external_intel_review_candidates_20261119_234734.csv`, not in Discovery.

**Root cause:** these two never had a regular writer. Their history was a one-off side effect of the macro lane on 21 Aug, frozen at 20 Aug by the migration.

## 5. Can the board's own fill close a gap this long?

`macro_board/market_prices.py` `plan_fill` (`:61-93`) uses `max_gap_sessions = 120` (config `:550`). Commits: `af2d4e8` (9 Oct) added the fill; `d6d780f` (10 Oct) changed it so cached sessions don't count against the limit.

- **Live builds: yes, today.** The cache `macro_board/output/cache/grouped/` holds all 130 sessions from 18 May to 19 Nov, with no missing cells for the 39 (102 MB, every US ticker per session). Its first files were written on 10 Oct, when the gap was about 100 sessions, under the limit. The 19 Nov evening build's fill report:
  - filled 130 sessions for each of the 37 and 64 for RSP and UUP;
  - `gap_too_long` empty;
  - `metrics.status = FRESH` for IJR, RSP and UUP.
- **It is fragile:**
  - **Cache loss means a permanent refusal.** Without the cache, the 37 need 130 sessions (more than 120), so they are reported `gap_too_long` and stay STALE. The gap grows by one session a day.
  - **As-of builds never fill** (`build_board.py:208`). Every historical or acceptance rebuild shows the 39 as STALE, so their reads are MISSING. That is what T7 saw.
  - **History depth.** The fill only goes back to the last stored bar, so the 37 have 193 sessions on the board (store 63 + fill 130). `vs_sma200` is null, the 252-session high uses 193 sessions, and the conditional evidence (from `history_start` 2020-06-01) only covers Feb 2026 onward.
  - **Splits.** Each cached session is split-adjusted as of the day it was fetched and is never revised. A split after that date makes a false jump. **BITO now:** cached close 18 Nov 8.31, 19 Nov 16.48 (×1.983, volume 62.3M → 11.7M). The live board shows ret_1d +98.3%, ret_20d +51.7%, rv20 251%, from_252_high 0. The 37 include 18 leveraged or inverse ETFs, which reverse-split often, so this will recur.
- **Not a reason for the gap:** none of the 39 is a rotation sector or industry ETF. `triage_context.links_from_store` reads the store directly but only for the stock-to-rotation-ETF links, so it is unaffected.

## 6. What a safe one-time backfill would need (not done)

- **Sources already on disk. No provider calls and no MarketData credits.**
  - `Enhancements/direction_evidence/survivorship/grouped_daily/*.parquet`: Polygon grouped daily, adjusted, 1,253 sessions from 2021-10-08 to 2026-10-06. All 39 are present, except BITO and GBTC on the earliest dates (BITO listed in Oct 2021; GBTC was OTC until Jan 2024).
  - `macro_board/output/cache/grouped/`: 18 May to 19 Nov.
- **Seam checks done read-only:**
  - archive close = store close on 15 May (IJR 133.93 in both);
  - archive = board cache on 18 May and 6 Oct for all 39 (no difference above 0.5%).
- **The split problem rules out stitching the files as they are.** A one-time backfill must re-adjust to one point in time. The cleanest way is a fresh per-ticker Polygon aggregates call (`/v2/aggs/ticker/{T}/range/1/day/2021-08-23/<today>`, adjusted). That is **39 calls**, with no MarketData credits, all bars adjusted as of today. The on-disk files are then used only as an independent check.
- **Tables:** `ohlcv_daily`, `ohlcv_ingest_batches` and `ohlcv_daily_revisions`, written only through `canonical_data/historical_prices.py:249` `HistoricalPriceDatabase.ingest`, so batches, hashes and provenance are kept.
  - New `source_kind`, for example `BOARD_UNIVERSE_BACKFILL`.
  - Full SQLite backup first, receipt per ticker, dry run first. This is the same pattern as the 7 Oct backfill.
  - The existing 63 rows and the 20 Aug-and-earlier rows would differ from today's adjustment wherever a split happened since. They become recorded revisions; they are not overwritten silently.
- **Timing:** only when no pipeline run is live, and run by ACK.

## 7. Fix options (for ACK's decision; no code until approved)

**Option A: board only, harden the fill (pipeline untouched).**
- Re-fetch or re-adjust the cached sessions when a jump consistent with a split appears. For example, detect it from the grouped `v` and `c` ratio, or call Polygon `/v3/reference/splits` for universe ETFs on refresh builds.
- Let `--as-of` builds use cached sessions on or before the as-of date.
- Report cache loss loudly.
- **For:** keeps ACK's 9 Oct rule that the board never writes the store, and it is small.
- **Against:** history depth stays at 193 sessions for the 37. The 102 MB cache becomes a primary record the pipeline cannot see. Every consumer other than the board still sees 15 May and 20 Aug.

**Option B (recommended): one-time store backfill plus a governed daily writer for the board universe.**
- Do the backfill in section 6.
- Then add a small daily step in `Run-MacroInputs.ps1` post-close (or an orchestrator step) that ingests the board's 115 universe ETFs into the store with `HistoricalPriceDatabase.ingest`. The board already fetches that grouped session each day, so this costs at most one Polygon call.
- Add a split check that, when a split is found, re-fetches that ticker's full adjusted history.
- **For:** one source of truth, full 5-year depth, as-of builds work, and the fill goes back to being a pre-store safety net.
- **Against:** it changes the "store is never written by the board" rule, so it needs ACK's approval. It adds a store writer outside Discovery.

**Option C: put the 39 back in the Discovery universe (`polygon_liquid_universe.csv`).**
- **For:** reuses the existing writer, with no new code path.
- **Against:**
  - The ETFs become Discovery candidates, including 18 leveraged or inverse ones. That changes what the pipeline ranks and hands to the Lab.
  - It reverses the 16 May universe choice.
  - It would also need the history backfill.
  - The scanner-injection route (`scripts/avshunter_universe_scanner.py:168`) is no substitute: it fetched TQQQ in only 16 of 31 runs since 24 Aug.

**Separate from any option:** the BITO false read is live on the current board. It is part of whichever option ACK picks (A's split check, or B's re-fetch), but it may deserve a quick label in the meantime.

## 8. What stays MISSING or wrong on the board until fixed

- **Live (evening, morning, intraday) builds while the cache is intact:**
  - None of the 39 shows STALE or MISSING.
  - **BITO is wrong.** It shows false returns, vol and range since 19 Nov, and every later session builds on the unadjusted history.
  - **For the 37, `vs_sma200` is MISSING** (null), and 252-session and long-window evidence is thin (193 sessions).
- **As-of rebuilds (T7 acceptance, replays):**
  - All 39 are STALE, and their own reads are MISSING with the last session named. On the 19 Nov as-of split count that is 18 MISSING.
  - RSP as a peer is MISSING. This is now moot, because ACK chose `EW_SECTORS` on 20 Nov.
  - **RSP is still used outside T7.** `macro_board/opportunity.py:40` reads RSP against SPY over 20 sessions as a breadth read. On an as-of build it takes RSP's 20 Aug metrics, so it is not checked here whether that read is labelled stale. This needs checking under any option.
- **If the grouped cache is lost:**
  - The 37 stay STALE on every build, as `gap_too_long`.
  - RSP and UUP refill only while their gap is 120 sessions or fewer (64 today, so about 56 more sessions).
- **For ACK's information:** the 20 Nov peer decision was taken on the as-of view, where RSP is stale. On live builds RSP is FRESH through the fill. `EW_SECTORS` remains ACK's choice; this note does not reopen it.

## 9. Not verified

- The BITO split has not been checked against a splits feed. No provider calls were made.
- Who replaced the universe on 16 May, and why, is not in git. Only file timestamps show it.
- The next live build after T7 has not been inspected, because no build was run. The live T7 projection file (`etf_intelligence_latest.json`) does not exist yet.

## 10. ACK decision and build (20 Nov 2026)

**ACK chose option B** ("option B", 20 Nov 2026). Built in worktree branch `claude/vibrant-blackburn-eede6a` (based on `ff24d41`); not committed, not merged into the main checkout.

**What was built**
- `macro_board/store_writer.py` (new). A separate step; the board build stays read-only on the store.
  - **Daily** (default): inserts the completed sessions the store lacks for the board universe (115 ETFs) from the board's grouped bars (cached sessions cost no call). It never revises a stored value. A gap above `max_daily_gap_sessions` (10) is left whole and reported for the backfill.
  - **Splits:** one Polygon splits call covers the window. A listed split re-fetches that ticker's full adjusted history; the old rows become recorded revisions. Without the split check, nothing is written.
  - **Unexplained jump:** a close ratio beyond `jump_hold_ratio` (1.45 either way) with no listed split is held, not written. ACK checks it, then `--refetch TICKER`.
  - **Backfill** (one time): `--backfill` fetches each long-gap or never-stored ticker's adjusted history once and saves it with `review.json` (no store write). `--execute DIR` takes a SQLite backup and writes exactly the saved bars through `HistoricalPriceDatabase.ingest`, `source_kind = BOARD_UNIVERSE_BACKFILL`. `--accept` releases tickers held only for `INTERNAL_JUMP`, after ACK checks them. Execute refuses a store other than the one reviewed.
  - Exit codes: 0 all written or up to date; 2 something held or left for the backfill (named in the receipt; the board is unaffected); 1 error.
- `macro_board/config/board_store_writer_v1.json` (new): limits with rationale. Settle margin, history start and price store come from the board config (one owner).
- `Run-MacroInputs.ps1`: one step, `store_writer`, just before `board` (skipped with `-SkipBoard`; exit 0 or 2 accepted).
- `macro_board/tests/test_store_writer.py`: 14 business-rule tests, all pass. `test_market_prices.py` still passes (12).

**Backfill dry run, 20 Nov 18:08 UTC** (`Enhancements/macro_board/store_backfill/20261120T180808Z/`): read-only on the store, 39 Polygon calls, 0 MarketData credits.
- Scope is exactly the 39. History from 2021-11-22 (Polygon's 5-year limit), through 19 Nov. 48,876 rows.
- 35 READY. 306 stored rows will become recorded revisions.
- **Splits since the stored rows, now corrected:** BITO and BOIL (all 63 stored rows differ, ratio 2: 1-for-2 reverse splits), SOXS and TZA (ratio 10: 1-for-10). BITO's false +98% on the board goes once these are in the store.
- **4 held for INTERNAL_JUMP, all checked as real moves:** SOXL +55% / SOXS −56% on 9 Apr 2025 (the tariff-pause day); SOXL −39% / SOXS +39% on 5 Nov 2026 (SMH −11%, SOXX −12% in the board's cache); BOIL/KOLD on 14 Jun 2022, 20 Jan 2026 and 2 Feb 2026, each mirrored by the other. Recommended: `--accept BOIL KOLD SOXL SOXS`.
- Every ticker shows 2025-01-09 as a missing session: that day markets closed (national day of mourning), so this is the calendar counting it, not a data hole. GBTC also lacks 4 sessions in Dec 2022 (OTC era).

**Still open**
- The execute has not been run. It is ACK's to run, when no pipeline is writing the store.
- The daily step's 1.45 hold will also hold real leveraged-ETF moves of that size (held and reported, never written wrong). Review on the receipts.
- `macro_board/market_prices.py` docstring and the board config `prices.rationale` still say the store is never written; reword once this is merged.
- `avshunter.shared.xnys_calendar` treats 2025-01-09 as a session (follow-up, not part of this fix).
- `opportunity.py:40` (RSP vs SPY on as-of builds) is covered once RSP is in the store; check on the first as-of rebuild after the execute.
