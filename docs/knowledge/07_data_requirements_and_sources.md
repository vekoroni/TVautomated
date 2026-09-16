# 07 — Data Requirements and Sources

Status: **Draft** · Capability: O8 Trustworthy operation · Context: C1 Market Data

## Question this note answers

> What data does each method need, how must it be captured to be point-in-time, and where does it come from?

## Point-in-time capture rules

1. Every dataset stored with `observed_at` (when we captured it), `as_of` (market time it describes), provider, request parameters and a content hash.
2. Never overwrite: revisions are appended; readers request `as_of` explicitly.
3. "Latest" files are views over the store, never inputs to a decision.
4. Missing capture is recorded as missing for that session — never back-filled silently.

## Requirements by method

| Method (note) | Data | Status in AVSHUNTER (16 Sep 2026) | Source |
|---|---|---|---|
| Evidence, first-passage (01) | Daily OHLCV, split/dividend adjusted, with open/high/low for barrier and gap logic | **Available**: `historical_prices.sqlite` 2021-08 → current, revision table; needs outlier validation and as-of reader | Polygon/Massive aggregates |
| Evidence (01) | Point-in-time universe incl. delisted tickers | **Gap**: universe file overwritten; survivorship unproven | Polygon reference tickers (active + delisted) [to confirm plan access] |
| Evidence (01) | Corporate actions (splits, dividends) | Partial (adjusted bars) | Polygon/Massive splits & dividends endpoints [to confirm] |
| Direction / thesis (02) | Structural levels from bars | Available (derived) | Internal |
| Valuation (03) | Option chains per session: bid/ask, sizes, OI, volume, IV, greeks, provider timestamps | **Available** from 2026-08-28 in canonical observations; weekly phantom snapshots earlier (partial) | MarketData.app chains |
| Valuation (03) | Risk-free rate curve | Defaulted in EV3 | FRED (T-bill) |
| Valuation (03) | Dividend schedule / yield | Defaulted | Polygon/Massive dividends [to confirm] |
| Valuation (03) | Commission schedule, actual fills | Journal (14 trades, unlinked) | Broker statements |
| Valuation — short shares (03) | Borrow availability, borrow fee, hard-to-borrow | **Gap** | Tastytrade `/market-metrics` `borrow_rate` (OAuth required since 1 Dec 2025); IBKR; ORTEX |
| Evidence feature (01/02) | Short interest (bi-weekly FINRA), short volume (daily) | **Available, unused** — verified live with existing key | Polygon/Massive `/stocks/v1/short-interest`, `/stocks/v1/short-volume` |
| Volatility (04) | Realised volatility inputs | Available (bars) | Internal |
| Volatility (04) | **Daily** IV history (30-day constant maturity) ≥ 252 sessions | **Gap**: `iv_history_cache.db` weekly, stale, ≤ 55 rows/ticker | Build from daily chain capture going forward; Tastytrade IV rank/percentile snapshot; vendor backfill |
| Volatility (04) | Earnings calendar (date, before/after market, estimated vs confirmed) | **Available, unused** — verified live with existing key; current morning field does not exist | MarketData.app `/v1/stocks/earnings/{symbol}/`; Tastytrade earnings expected date |
| Volatility (04) | Historical earnings-day moves | Derivable | Bars + earnings history |
| Ranking (05) | Sector / industry classification (point-in-time) | Partial (universe CSV) | Polygon/Massive reference data |
| Validation (06) | Decision ledger with complete inputs, matured outcomes, linked fills | **Gap**: required fields null | Internal (recording contract) |
| Macro context (advisory) | Dated macro context file | Scheduled cloud routine | Internal routine |

## Provider notes

| Provider | Credential present | Verified use |
|---|---|---|
| MarketData.app | `MARKETDATA_API_KEY` | Chains, quotes, candles; earnings endpoint works (not used) |
| Polygon / Massive (plan "Stock Screener Standard") | `POLYGON_API_KEY` | Aggregates; short interest and short volume work (not used); ticker snapshot has **no** earnings field |
| Tastytrade | **None configured** | Existing client uses discontinued `/sessions` login; OAuth app required for market metrics |
| FRED | — | Used by macro build (now external) |

## Open data decisions

1. Tastytrade OAuth integration for borrow rate and volatility metrics (user to create OAuth app).
2. Vendor backfill of daily IV history vs building forward from daily capture (≥ 12 months to reach a 252-session IVP).
3. Point-in-time universe including delisted names (confirm Polygon plan access).
