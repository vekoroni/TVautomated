# Intraday data completeness and accuracy: root cause and fix design (12 Oct 2026)

Status: ROOT CAUSE + FIX DESIGN FOR ACK APPROVAL. Step 1 of `DISCOVERY_VANGUARD_BEHAVIOURAL_STAGE_DESIGN_20261012.md`
(section 4). Evidence: the canonical registry (`control_plane.sqlite`, 830,656 five-minute session records), the
10 Oct completed-profile receipt, the daily store, read-only checks on 8-9 Oct sessions.

## Why it matters

The behavioural stage reads 60m, 15m and 5m from the stored five-minute bars (swing, setup, trigger and response).
On 10 Oct, 47% of candidates carried STALE_INTRADAY or INCOMPLETE_SESSIONS, so the lower-timeframe reading was of
an older day or a broken one. An accurate reading makes the human judgement easier; an inaccurate one misleads it.

## Root causes

| ID | Cause | Evidence |
|---|---|---|
| RC-I1 | **Sessions are captured only as a side effect of runs, one session per run, with no catch-up.** The Evening writer (`scripts/build_completed_market_profiles.py`) fetches only the last completed session at run time; a session with no Evening after it is never captured | Whole sessions absent or partial for every ticker: 15 Sep, 28 Sep (488 partial, 0 complete), 30 Sep, 6 Oct (51 partial). 7 Sep is Labor Day and 26 Sep a Saturday (correctly absent) |
| RC-I2 | **Provider "no data" is recorded as an inactive ticker.** MarketData returned no five-minute candles; the stage deferred the ticker as TICKER_INACTIVE with no retry and no second source | 9 Oct: 600 Discovery tickers had no session record; **456 traded that day** in the daily store (median 151k shares, $36); DXC, ELME, IHRT, SPWR, UTZ traded > 1M shares |
| RC-I3 | **A truncated morning capture is labelled COMPLETE and preferred over the full day.** Completeness is judged against the requested window (open to the capture time), not the session; the Discovery index then keeps the latest COMPLETE record, ranking it above a full-day PARTIAL | Of 300 sampled 9 Oct COMPLETE records, 142 end at 10:15 ET (Morning capture); 23 of those closes differ from the official close by > 2% (0 of the full-day records do) |
| RC-I4 | **Full-day sessions of thinly traded names are rejected.** No-trade five-minute intervals make the session PARTIAL (MISSING_INTERVALS) and the index uses COMPLETE only. ACK's 5 Oct rule ("a partial session on a thin name is a ticker fact") was applied to market profiles, not to the behavioural reading | 9 Oct: 651 partial (median daily volume 347k vs 1.9M for complete); 278-345 thin-name partials per Evening |
| RC-I5 (definition) | Regular-session five-minute volume excludes extended hours and the closing auction | Summed volume is ~34% below the daily bar on every sampled session; high / low agree (median 0) |

## Fix design (test-first; replayed on the stored registry; no provider call in tests)

| Fix | Change | Owner |
|---|---|---|
| F1 (RC-I3) | A session record states **what it covers**: `SESSION_COMPLETE` (open to close present), `SESSION_COMPLETE_SPARSE` (open and close edges present, no-trade intervals inside, daily bar shows trading), `WINDOW_ONLY` (in-progress capture). The Discovery index serves a completed session only from SESSION_COMPLETE(_SPARSE); WINDOW_ONLY stays available to the Morning's own intraday read, labelled. Existing records are re-classified from their own bars (last bar vs session close) - no refetch | `canonical_data/intraday_bars.py` (quality + index) |
| F2 (RC-I4) | Thin names: SESSION_COMPLETE_SPARSE is usable; the reading knows which intervals had no trades (never filled, never invented) | same |
| F3 (RC-I1) | **Catch-up:** each Evening resolves every missing completed session inside the reading window (the engine's 60m / 15m / 5m session windows from `config/beh001_behaviour_v1.json`), not only the last; a one-off governed backfill closes the current gaps (15 Sep, 28 Sep, 30 Sep, 6 Oct and per-ticker gaps). Budgeted and resumable; ACK runs it | Evening intraday stage; `scripts/backfill_polygon_intraday.py` path |
| F4 (RC-I2) | Provider no-data for a ticker that traded (daily volume > 0): retry, then the second source for underlying bars (Polygon aggregates, already used for daily bars and the backfill), labelled with its provider. TICKER_INACTIVE only when the daily bar shows no trading | Evening intraday stage |
| F5 (accuracy) | Every stored session reconciles to its daily bar (high, low, open, close within a governed tolerance in config); outliers flagged `INTRADAY_DISAGREES_WITH_DAILY`, and the behavioural reading on that timeframe is capped at INFERRED (design 2.1) | quality check at write + Evening scorecard (report) |
| F6 (RC-I5) | Volume basis labelled `REGULAR_SESSION`; relative-volume enhancers compare like with like | enhancer definitions (step 6) |

## Acceptance

- Replay the Discovery index on 10 Oct before / after F1-F2 (no fetch): STALE_INTRADAY and INCOMPLETE_SESSIONS counts,
  truncated sessions served as complete (target 0).
- After the F3 / F4 backfill (ACK runs): session coverage per day vs tickers that traded that day (daily store) - target
  every traded ticker covered or labelled with the provider reason; the 30 Sep sessions present.
- F5 reconciliation report on the whole store: outlier count and the tickers affected.
- Evening scorecard: intraday coverage and reconciliation as report-only checks.

## Decisions for ACK

1. F4 source: Polygon aggregates as the second source for underlying intraday bars (options stay MarketData only).
2. F3 backfill: run the one-off catch-up (ACK runs it; not while a pipeline or Phantom backfill is writing).
3. F5 tolerance: initial 0.5% on high / low / close (to be calibrated on the reconciliation report).
