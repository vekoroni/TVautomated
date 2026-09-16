# 07 — Data Requirements and Sources

Status: **Draft v2** (reconciled to specification v1.1, 16 Sep 2026) · Capability: O8 Trustworthy operation · Contexts: **C1 Market Data, C2 Universe & Eligibility** · Governing: spec §4–§6, Invariant F

## Question this note answers

> What data does each method need, how must it be captured to be point-in-time and fresh, and where does it come from?

## Point-in-time capture rules

1. Every dataset stored with `observed_at` (when we captured it), `as_of` (market time it describes), provider, request parameters and a content hash.
2. Never overwrite: revisions are appended; readers request `as_of` explicitly.
3. "Latest" files are views over the store, never inputs to a decision.
4. Missing capture is recorded as missing for that session — never back-filled silently; a later backfill is recorded as such with its own `observed_at`.
5. **Fixed capture panel**: the eligible universe plus benchmark instruments (SPY, QQQ) is captured every evening — not only candidates (candidate-only capture creates selection-biased history).
6. **Freshness**: every consumer declares the session it needs; older data is `STALE_HISTORY`, never COMPLETE; capture coverage below threshold is a run-health failure.
7. **Provider request shape**: historical-only parameters (e.g. MarketData `date`) are sent only for past sessions.

## Requirements by method

| Method (note) | Data | Status in AVSHUNTER (16 Sep 2026) | Source |
|---|---|---|---|
| Evidence, first-passage (01) | Daily OHLCV, split/dividend adjusted, open/high/low for barrier and gap logic; path store sessions 1..20 | **Available**: `historical_prices.sqlite` 2021-08 → 2026-09-14, revision table; needs outlier validation, as-of reader and path store | Polygon/Massive aggregates |
| Evidence / eligibility (01, C2) | Point-in-time universe incl. delisted tickers | **Gap**: universe file overwritten; survivorship unproven | Polygon reference tickers (active + delisted) [to confirm plan access] |
| Evidence (01) | Corporate actions (splits, dividends) | Partial (adjusted bars) | Polygon/Massive splits & dividends endpoints [to confirm] |
| Structure / geometries (02) | Structural levels from bars | Available (derived) | Internal |
| Structure — dealer positioning (C3) | Per-ticker chains with OI and gamma; SPY/QQQ chains | Per-ticker chains available for candidates; **SPY/QQQ not captured since session 2026-09-04** (acquisition fails on `date`); GEX logic defective | MarketData.app chains |
| Valuation (03) | Option chains per session: bid/ask, sizes, OI (with as-of), volume, IV, greeks, provider timestamps | **Partial**: daily canonical chains for candidates since 2026-08-28 (9 sessions); Phantom weekly full-universe snapshots since ~May 2024 with missing weeks; **full-universe history stale since 2026-09-04** (manual weekly backfill); 28 Aug–10 Sep canonical chains not projected to history | MarketData.app chains; historical `date` queries for backfill (~1 credit per ticker per session) |
| Valuation (03) | Risk-free rate curve | Defaulted in EV3 | FRED (T-bill) |
| Valuation (03) | Dividend schedule / yield | Defaulted | Polygon/Massive dividends [to confirm] |
| Valuation (03) | Commission schedule, actual fills | Journal (14 trades, unlinked) | Broker statements |
| Valuation — short shares (03) | Borrow availability, borrow fee, hard-to-borrow | **Gap** → `BORROW_DATA_UNAVAILABLE` | Tastytrade `/market-metrics` `borrow_rate` (OAuth required since 1 Dec 2025); IBKR; ORTEX |
| Evidence feature (01/02) | Short interest (bi-weekly FINRA), short volume (daily) | **Available, unused** — verified live with existing key | Polygon/Massive `/stocks/v1/short-interest`, `/stocks/v1/short-volume` |
| Volatility (04) | Realised volatility inputs | Available (bars) | Internal |
| Volatility (04) | **Daily** constant-maturity 30-day IV series ≥ 252 sessions | **Gap** (daily). Weekly per-contract IV in Phantom `chain_snapshots` since ~May 2024 (interim seed); `iv_surface_history` 10 weekly dates; `iv_history_cache.db` sparse (≈7 samples/ticker), last 2026-09-04 | Derive from daily panel capture going forward; weekly Phantom history as interim; Tastytrade IV rank/percentile snapshot; vendor backfill |
| Volatility (04) | Earnings calendar (date, before/after market, estimated vs confirmed) | **Available, unused** — verified live with existing key; current morning field does not exist | MarketData.app `/v1/stocks/earnings/{symbol}/`; Tastytrade earnings expected date |
| Volatility (04) | Historical earnings-day moves | Derivable | Bars + earnings history |
| Ranking (05) | Sector / industry classification (point-in-time) | Partial (universe CSV) | Polygon/Massive reference data |
| Validation (06) | Ledger with complete lineage for every record type; underlying and expression outcomes | **Gap**: required fields null; option leg absent | Internal (C11/C12 contract) |
| Configuration (all) | Versioned thresholds, bands, tolerances with validation state | **Gap** | Internal (spec Appendix B) |
| Macro context (display only) | Dated macro context file | Scheduled cloud routine | Internal routine |

## Provider notes

| Provider | Credential present | Verified use |
|---|---|---|
| MarketData.app | `MARKETDATA_API_KEY` | Chains, quotes, candles; historical chains with `date` for past sessions; `date` rejected for the current session; earnings endpoint works (not used) |
| Polygon / Massive (plan "Stock Screener Standard") | `POLYGON_API_KEY` | Aggregates; short interest and short volume work (not used); ticker snapshot has **no** earnings field |
| Tastytrade | **None configured** | Existing client uses discontinued `/sessions` login; OAuth app required for market metrics |
| FRED | — | Used by macro build (now external) |

Keys to be rotated by ACK after the build is complete.

## Open data decisions

1. Tastytrade OAuth integration for borrow rate and volatility metrics (ACK to create OAuth app).
2. Vendor backfill of daily IV history vs building forward from daily panel capture (≥ 12 months to reach a 252-session IVP) — interim use of weekly Phantom history.
3. Point-in-time universe including delisted names (confirm Polygon plan access).
4. Backfill scope and credit budget for missed full-universe sessions (first Phase 0 data task, before replications R1/R4).
