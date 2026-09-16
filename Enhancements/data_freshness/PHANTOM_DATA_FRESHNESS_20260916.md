# Phantom database freshness (16 Sep 2026)

Owner expectation: the Phantom database updates every time the evening pipeline runs. Read-only validation.

## What updates and what does not

| Phantom content | Last written | Updated by evening run? |
|---|---|---|
| `phantom_scores` (edge-model scores) | 15 Sep 00:46 (run 20260914_214012); every evening run since 06 Sep | **Yes** (`phantom_engine.py`, Phase 7.5). Reads history, writes scores only. |
| `chain_snapshots`, **candidate tickers only** (~1,300) | Sessions 11 Sep and 14 Sep | **Only since 13 Sep** (commit `a883c36`, canonical→Phantom projection, `intelligent_orchestrator.py` ~L5188) |
| `chain_snapshots`, **full universe** (~2,900 tickers) | Session **04 Sep** (written 05 Sep 10:16 UTC) | **No.** Manual weekly backfill (`backfill_audit`, backups `*.pre_weekly_maintenance_20260905_*`). No scheduled task exists. |
| `options_greeks_history` (recomputed greeks) | Session 04 Sep (05 Sep 10:30 UTC) | **No.** Weekly maintenance only. |
| `iv_surface_history` | Session 04 Sep | **No.** Weekly maintenance only. |
| `data/cache/iv_history_cache.db` | Refresh 04 Sep | **No.** |
| SPY / QQQ chains (for GEX) | Session 04 Sep | **No.** Not candidates; the evening SPY/QQQ refresh fails at MarketData (see `../gex/` §7). |
| `data/canonical/historical_prices.sqlite` (for comparison) | 14 Sep, 2,995 tickers | Yes |

## Root causes

1. **Full-universe option history was never part of the evening pipeline.** It comes from a manually run weekly backfill. The last run was 05 Sep (session 04 Sep); the 11 Sep weekly snapshot was never run. Windows Task Scheduler has no Phantom/backfill task (only MA Cockpit and News Terminal tasks).
2. **Evening chain capture started on 13 Sep and covers candidates only.** Chains the evening run acquired on 28 Aug–10 Sep sit in `data/canonical/market_observations/option_chain/` but were never projected (the outbox only holds events created after the feature landed).
3. **Derived history (recomputed greeks, IV surface, IV cache) only runs inside weekly maintenance,** so it is stale with it.
4. **SPY/QQQ acquisition fails** (`date` parameter rejected for the current session), so GEX has no new benchmark chains.
5. **No freshness control.** No stage checks that history is current for the evidence session. Phantom scoring, GEX (`build_local_gex` reports COMPLETE on 04 Sep data) and IV measures silently use 12-day-old data.

Note: historical MarketData queries with `date` do work for past sessions (the 05 Sep backfill fetched session 04 Sep at ~1 estimated credit per ticker), so the missing sessions can be backfilled.

## Correct fix design (not implemented, awaiting approval)

Market Data context in the rebuild:

1. **One capture stage owned by the evening run** for a fixed panel (eligible universe + SPY/QQQ), not candidates only. It writes chains to canonical storage and projects them to history in the same run, with a receipt per ticker/session.
2. **Derived history in the same run:** recomputed greeks with quality state, daily 30-day constant-maturity ATM IV, IV surface, and GEX, all keyed to the evidence session.
3. **Freshness gate:** every consumer declares the session it needs. History older than the evidence session gives `STALE_HISTORY` (never COMPLETE, never a silent fallback), and the run report lists stale datasets.
4. **Backfill:** project the unprojected canonical chains (28 Aug–10 Sep); fetch the full-universe session 11 Sep (and any later missed session) via historical `date` queries; fill the earlier missing weeks if credits allow.
5. **Run health:** the evening run fails loudly (visible in the run manifest and Lab) when capture coverage drops below a threshold, rather than logging a warning and continuing.
