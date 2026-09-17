# Phase 0 — Foundation / Data Truth: Plan and Backfill Design

| Item | Value |
|---|---|
| Version | 1.0 (16 Sep 2026) |
| Status | **For ACK approval.** No code changed, no API calls made, no data written. |
| Governed by | Specification v1.1 (§4, §5, §6, §15, §24, Appendix B); end-to-end map and migration design v2.0 (§7 Phase 0, S0, S1, S2, S17); `CLAUDE.md` |
| Evidence | `../data_freshness/PHANTOM_DATA_FRESHNESS_20260916.md`, `../iv_history/IV_HISTORY_INVENTORY_20260916.md`, dry run of `scripts/run_phantom_backfill_parallel.py` (16 Sep) |

---

## 1. Phase 0 scope and order

Phase 0 changes no trading logic. It establishes the clock, release, configuration, data truth, universe and ledger that every later context depends on. Exit criterion (end-to-end §7): clean-tree runs only; capture coverage and freshness reported and above threshold for 5 consecutive sessions; replay reproduces golden runs; eligibility reasons sum to the universe.

| # | Workstream | Context | Deliverable | Depends on | Code? |
|---|---|---|---|---|---|
| **P0-1** | **History backfill (this document §2–§6)** | C1 | Phantom history current and gap-free for the capture panel; daily sessions since 2026-08-28 | — | No new code (existing tool, existing CLI) |
| P0-2 | Configuration registry | C0 | Versioned configuration store with `config_key, value, unit, effective_from, version, business_owner, validation_state, rationale`; initial register (spec Appendix B) | — | Yes (design to follow) |
| P0-3 | Run context and release gate | C0 | Single launcher, injected clock, `release_id`, `clean_tree`, pre-flight gate, `conftest.py` with injected clock | P0-2 | Yes |
| P0-4 | Chain acquisition adapter and capture panel | C1 | One adapter (`date` only for past sessions); nightly fixed panel (universe + SPY/QQQ) written and projected in the same run with receipts; freshness gate; run-health coverage | P0-2, P0-3 | Yes |
| P0-5 | Point-in-time universe and capabilities | C2 | Membership table incl. delisted names, eligibility reason codes, instrument capabilities | P0-4 | Yes (data access to delisted names to confirm) |
| P0-6 | Ledger record contract | C11 | Record types and required lineage for every context; refusal of incomplete records; legacy rows kept separate | P0-3 | Yes |
| P0-7 | Hygiene and baselines | C0 | Untracked production imports resolved; test rows quarantined; 3 golden run snapshots; nightly real-run gate (extends `decision_map_coverage.py`); overnight macro-file overwrite stopped | P0-3 | Mixed |

Each code workstream (P0-2 … P0-7) gets its own short design for approval before implementation, per `CLAUDE.md`. P0-1 runs first because replications R1/R4 and every later context need complete, fresh history, and history cannot be recaptured retrospectively except through the provider's historical endpoint.

---

## 2. Backfill — current state (verified 16 Sep 2026)

| Item | Finding |
|---|---|
| Capture panel used by the weekly backfill | `data/universe/polygon_liquid_universe.csv` — 3,318 tickers (file last modified 2026-05-17; not point-in-time — fixed in P0-5) |
| Weekly full-panel history | Fridays; full panel (3,318) on 2026-07-31, 08-28, 09-04; only 1,380 tickers on 05-22 … 07-17 |
| Missing weekly sessions | 2026-07-24, 08-07, 08-14, 08-21 (whole panel); 1,938 tickers on each of 05-22, 05-29, 06-05, 06-12, 06-26, 07-10, 07-17 |
| Not gaps | 2026-04-03, 06-19, 07-03 are market holidays (`NO_DATA` for all tickers) |
| Dry run (no API calls), weekly, 12 months to 2026-09-11 | 175,854 planned; 288,290 completed keys; **60,245 remaining** before no-data stops |
| Daily history | None before 2026-08-28. Evening-run candidate chains (≈1,300 tickers) projected to Phantom only for 09-11 and 09-14 |
| Request shape (existing history) | `date`, `from = date+7d`, `to = date+60d`, `strikeLimit = 40`, `range = all`, `minOpenInterest = 1` |
| Cost per request | ≈ 1 credit (tool estimate `ceil(rows/1000)`; audit: 3,320 credits for 3,318 tickers on 09-04) |
| Credit allowance | 100,000 credits/day, reset 09:30 ET — **paid tier, validated and tested by ACK (16 Sep 2026)** |
| Write behaviour | `INSERT … ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE` — re-fetching a (ticker, session) that already exists **overwrites** it; resume is keyed on `backfill_audit` query keys |
| Runtime | ≈ 40–50 minutes per full-panel session with 6 workers |

---

## 3. Backfill design

### 3.1 Principles

1. **Consistency with existing history**: use the existing, audited tool and the same request shape as the weekly history, so the series is homogeneous.
2. **Never overwrite captured data**: a (ticker, session) already present in `chain_snapshots` is not requested again. Sessions partly present are requested only for the missing tickers (`--tickers`).
3. **Recent first**: daily sessions since 08-28 first (needed for freshness and the daily IV series), then weekly gaps newest-first.
4. **Bounded spend**: every batch runs with `--credit-cap`; total daily spend leaves headroom for the evening and morning pipelines.
5. **Out of hours**: batches run outside US market hours and not during the evening pipeline.
6. **Auditable**: every request is in `backfill_audit` (query key, params, status, rows, credits); each batch writes a receipt to `Enhancements/phase0/backfill_receipts/`.

### 3.2 Batches

| Batch | Sessions | Tickers | Est. requests / credits | Command pattern (existing CLI) |
|---|---|---|---|---|
| **B0 — Pre-check** (0 credits) | — | — | 0 | Dry runs for every batch below; disk space check |
| **B1 — Daily sessions, whole panel absent** | 2026-08-31, 09-01, 09-02, 09-03, 09-08, 09-09, 09-10, 09-15 | 3,318 each | ≈ 26,500 | one run per session: `--end-date <session> --weekday <session weekday> --years 0 --credit-cap 30000 --execute` |
| **B2 — Daily sessions, partly present** | 2026-09-11, 09-14 | tickers not already in `chain_snapshots` for that session (≈ 2,000 each) | ≈ 4,100 | as B1 plus `--tickers <missing list>` |
| **B3 — Weekly gaps** | Fridays 2025-09-12 … 2026-09-04 still missing (incl. 07-24, 08-07, 08-14, 08-21 and the 1,938-ticker gaps May–July) | per tool resume logic | ≤ 56,900 (60,245 minus the 09-11 session handled in B2) | `--end-date 2026-09-04 --years 1 --credit-cap <daily cap> --execute`, repeated on following days until remaining = 0 |
| **B4 — Post-processing** (0 credits, to confirm) | all backfilled sessions | — | 0 | `scripts/finalize_phantom_weekly_snapshot.py` for IV surface per session; greeks recomputation only via a solver path that makes no API calls (to be confirmed before running — `scripts/phantom_greek_rehydrate.py` issues chain requests) |
| **B5 — Verification** (0 credits) | all | — | 0 | §5 checks; receipt |

Totals: **≈ 31,000 credits for B1–B2** (one day) and **≤ 57,000 for B3** (spread over two days at ≤ 30,000/day). Upper bounds; no-data stops (newly listed or delisted names) reduce them.

Schedule (proposed): Day 1 — B0, B1, B2, B4, B5 for daily sessions. Days 2–3 — B3 in two capped batches, then B4/B5 for weekly sessions. From Day 1 onward, the evening session is added nightly by the same pattern until P0-4 replaces it with in-run capture.

### 3.3 Options considered and not recommended now

| Option | Why not now |
|---|---|
| Project the evening-run candidate chains of 08-28 … 09-10 into Phantom (0 credits) | Requires new code (these datasets predate the projection outbox); covers ~1,300 candidate tickers only (selection-biased); different quote source from the rest of history. B1 supersedes it. |
| Daily full-panel backfill for 252 sessions (daily IV series from day one) | ≈ 836,000 credits (≈ 8–9 days of the whole allowance). Decide after replication R2 shows whether weekly history is sufficient; the daily series builds forward from 08-28. |
| Wider request shape (no strike limit, all expiries) for GEX | Changes the history's shape and cost. Full-chain capture for GEX is designed in P0-4 for SPY/QQQ and the panel going forward. |
| Re-fetching sessions already captured to "refresh" them | Overwrites data that decisions used (upsert); violates append-only history. |

---

## 4. Risks and controls

| Risk | Control |
|---|---|
| Credit exhaustion affecting the evening/morning pipelines | `--credit-cap` per batch; ≤ 30,000/day; run after the evening pipeline completes (allowance 100,000/day validated by ACK) |
| Overwriting existing rows | Only absent (ticker, session) pairs requested; B2 uses explicit missing-ticker lists; dry-run counts compared with expected before `--execute` |
| Phantom DB (19.7 GB) corruption during long writes | Single serialized writer with WAL (existing tool); disk-space check (≥ 5 GB free) in B0; no concurrent pipeline run |
| Partial batch (network, rate limit) | Tool resumes from `backfill_audit` keys; rerun the same command |
| Universe file not point-in-time | Accepted for the backfill (same panel as existing history); P0-5 introduces the point-in-time universe; tickers added later are backfilled then |
| Rollback | All backfilled rows identifiable by (`quote_date` ∈ batch sessions, `created_at_utc` ≥ batch start, audit query keys); deletion script only with ACK approval |

---

## 5. Verification (B5)

For each backfilled session:

1. Tickers with rows + tickers with `NO_DATA` = panel size (3,318); errors = 0 or listed.
2. No (ticker, session) that existed before the batch changed (`created_at_utc` of pre-existing rows unchanged; row counts for pre-existing pairs unchanged).
3. Contract counts per ticker within the normal range for that ticker (median of its prior weekly sessions ± tolerance); outliers listed.
4. Quality: share of rows with IV ≤ 0.001, zero gamma or missing OI reported (quality states, not deletions).
5. Holiday check: no requests on XNYS holidays.
6. Freshness report: latest full-panel session per dataset equals the latest completed session.
7. Receipt written: sessions, tickers, requests, credits, rows, errors, checks passed/failed.

---

## 5a. Execution record

**Day 1 — B1 + B2 completed 16 Sep 2026, 18:27–21:13 UK** (`backfill_runbook.py`, receipts in `backfill_receipts/`):

| Session | Requests | OK | NO_DATA | Errors | Credits | Pre-existing tickers preserved |
|---|---|---|---|---|---|---|
| 2026-09-15 | 3,318 | 2,777 | 541 | 0 | 3,320 | yes |
| 2026-09-14 (missing only) | 2,003 | 1,463 | 540 | 0 | 2,005 | yes (1,316 kept) |
| 2026-09-11 (missing only) | 2,035 | 1,588 | 447 | 0 | 2,037 | yes (1,284 kept) |
| 2026-09-10, 09-09, 09-08, 09-02, 09-01, 08-31 | 3,318 each | 2,869 each | 449 each | 0 | 3,320 each | yes |
| 2026-09-03 | 3,316 | 2,868 | 448 | 0 | 3,318 | yes (2 kept) |
| **Total** | **30,580** | | | **0** | **30,600** | |

Follow-ups:
- **Late publication**: 09-14 and 09-15 show ~92 more `NO_DATA` tickers than older sessions (≈540 vs 449), consistent with provider historical data not yet published for the most recent sessions (the tool's default safety lag is 7 days). `NO_DATA` query keys count as completed, so a plain rerun would skip them: re-request those tickers explicitly with B3.
- **B4** (IV surface finalisation) not run on Day 1; not needed for the evening pipeline. Run with B3.
- **B3** weekly gaps: after the morning run on 17 Sep (credit allowance resets 14:30 UK), ≤ 30,000 credits/day.

**B3 part 1 — completed 17 Sep 2026, ~04:00–04:20 UK** (after the 16 Sep evening run completed; log `backfill_receipts/run_b3_day1.log`): weekly Fridays 2025-09-05 … 2026-09-04, newest first, cap 25,000.

| Results | OK | NO_DATA | Errors | Rows written | Credits |
|---|---|---|---|---|---|
| 25,011 | 18,291 | 6,720 | 0 | 1,232,708 | 25,011 |

Remaining after part 1 (dry run): **32,719** weekly requests (before no-data stops). Part 2 after the 17 Sep morning run (allowance resets 14:30 UK), together with the late-publication re-requests for 09-14/09-15 and B4.

## 6. Approvals requested

1. **Approve P0-1 backfill batches B0–B5** as designed, including API credit spend of ≈ 31,000 (Day 1) and ≤ 57,000 (Days 2–3), capped at ≤ 30,000 per day.
2. ~~Account check~~ — not needed: the 100,000 credits/day paid tier is validated (ACK, 16 Sep 2026).
3. **Confirm timing**: batches run outside US market hours and never during the evening or morning pipeline — tell me when the evening pipeline has finished on the day you want Day 1 to start.
4. **Approve the Phase 0 workstream order** (§1). Designs for P0-2 (configuration registry) and P0-3 (run context and release gate) follow next for approval.
