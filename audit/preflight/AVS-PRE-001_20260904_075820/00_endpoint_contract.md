# AVS-PRE-001 §2 — Endpoint contract read from the repository's own code

**Method:** read-only. No module below was imported; each was read as text. 0 HTTP requests.

---

## 1. The two MarketData candle callers in the repository

### 1.1 `scripts\backfill_timeseries_into_packages.py` — `marketdata_fetch_intraday_session` (:283-345)

Legacy LATEST-mode bridge. Fetches today's intraday candles and **collapses them into a single partial-session OHLCV bar**. Not the profile stage's path, but it establishes the house URL and auth convention.

```
URL     https://api.marketdata.app/v1/stocks/candles/{resolution}/{ticker}/?{params}
params  from=<YYYY-MM-DD>  to=<YYYY-MM-DD>  extended=false  adjustsplits=true
header  Authorization: Token {api_key}
method  GET, urllib, timeout 15
default resolution = 5
```

Response fields consumed: `s` (must equal `ok`, case-insensitive), `o`, `h`, `l`, `c`, `v`. **`t` is not read here** — the bar is aggregated, so timestamps are discarded.

### 1.2 `canonical_data\marketdata_stock_candles.py` — `MarketDataStockCandleAdapter.fetch_range` (:117-155)

The AVS-SD-002 Phase 3 frame-preserving adapter. **This is the path the completed-profile stage uses.**

```
URL     https://api.marketdata.app/v1/stocks/candles/{int(interval_minutes)}/{TICKER}/
params  from=<ISO-8601 UTC, "+00:00" replaced by "Z">
        to  =<ISO-8601 UTC, "+00:00" replaced by "Z">
        extended = "false" when session_segment == "REGULAR", else "true"
        adjustsplits = "true"
header  Authorization: Token {api_token}
method  GET, urllib, timeout 20 (default)
```

Note the difference from §1.1: `from`/`to` are **full ISO-8601 UTC instants**, not bare dates.

---

## 2. What the profile stage actually requests

`scripts\build_completed_market_profiles.py`:

- `--interval-minutes` default **5**, `choices=(1, 5, 15, 30)` (:196)
- session defaults to `session_snapshot(now).last_completed_session` (:203)
- calls `adapter.fetch_range(ticker, start, end, session_date=…, interval_minutes=…, session_segment="REGULAR")` (:113-116)
- the range is `session_bounds(session_date)` (:123) — i.e. **RTH only, 09:30–16:00 ET**, converted to UTC
- `invocation_id = f"{run_id}:completed-profile:{session_date}:{interval_minutes}"` (:126)

`canonical_data\session_clock.py:123-128`:

```python
open_local  = datetime.combine(value, time(9, 30), NEW_YORK)
close_local = datetime.combine(value, time(13 if is_early_close(value) else 16, 0), NEW_YORK)
return open_local.astimezone(timezone.utc), close_local.astimezone(timezone.utc)
```

**The preflight therefore requests exactly:** `interval=5`, `extended=false`, `adjustsplits=true`, `from=<session 09:30 ET as UTC Z>`, `to=<session 16:00 ET as UTC Z>`, header `Authorization: Token …`.

---

## 3. Parsing contract — `parse_marketdata_stock_candles` (:32-84)

This is what the provider response must satisfy, and every clause is a testable assumption:

| Assumption | Code | Consequence if the provider differs |
|---|---|---|
| `s` ∈ {`ok`, `success`} | `:45` | any other value raises `ValueError`, **except** `no_data`/`no data`/`nodata` which returns an empty frame (`:46-48`) |
| Parallel arrays `t,o,h,l,c,v` all present and **equal length** | `:51-58` | unequal lengths raise `ValueError: parallel-array length mismatch` |
| Values present but `t` empty ⇒ hard error | `:57-58` | `ValueError` |
| All arrays empty ⇒ empty frame, not an error | `:55-56` | — |
| Timestamps are **epoch numerics**, unit inferred: `ms` if `max(abs) ≥ 1e11` else `s` | `_timestamp_series` `:23-29` | a non-numeric (ISO string) array falls through to `pd.to_datetime(..., utc=True)`; a numeric array in any other unit is **silently misinterpreted** |
| `updated` / `observed_at` may be scalar or a parallel array of the same length | `:64-73` | a differently-sized array raises `ValueError` |
| `adjustment_convention` hard-coded `SPLIT_ADJUSTED` | `:151` | matches `adjustsplits=true` |
| `session_segment` is stamped from the **request**, not read from the response | `:78` | the provider is never asked to distinguish RTH from extended; the code asserts it |

`canonical_data\intraday_bars.py`:

- `SUPPORTED_INTERVALS = (1, 5, 15, 30)` (:28); anything else raises (:99-100)
- `expected_intraday_timestamps` (:149-165) builds bar-**open** timestamps on a `pd.date_range(start, close - interval, freq=f"{interval}min")` grid, RTH-clamped when `session_segment == "REGULAR"`
- `assess_intraday_quality` (:195-217) computes `coverage = observed∩expected / expected`, plus duplicate, missing and `OUTSIDE_REQUEST_SCOPE` (unexpected) counts

Expected RTH bar counts on a normal 09:30–16:00 session, from that grid: **390** (1-min), **78** (5-min), **26** (15-min), **13** (30-min). These match the counts §4 of the prompt asks for.

---

## 4. Assumptions this preflight will test

Each is a defect to file against the adapter if the provider disagrees (§5 answer 8):

- **A1** Timestamps are epoch **seconds** for this endpoint (the `ms`-vs-`s` inference at `:26-27` guesses from magnitude).
- **A2** Bar timestamps are bar-**open**, aligned to the `expected_intraday_timestamps` grid. If the provider returns bar-**close**, every bar is off by one interval and `coverage` collapses.
- **A3** `extended=false` yields RTH-only bars, so `session_segment="REGULAR"` stamped at `:78` is truthful.
- **A4** `from`/`to` accept full ISO-8601 `Z` instants (§1.2), not just bare dates (§1.1). The two callers disagree; only §1.2 is on the profile path.
- **A5** `to` is treated as **inclusive or exclusive** — the grid excludes the 16:00 bar (`inclusive_end = close - interval`), so a provider that returns a 16:00 bar produces an `OUTSIDE_REQUEST_SCOPE` flag.
- **A6** A no-data symbol returns `s="no_data"` and is classified as an empty frame rather than an error (`:46-48`). If the provider instead returns HTTP 404 or `s="error"`, `fetch_range` raises and the stage's per-ticker isolation must catch it.
- **A7** All six arrays are always the same length — in particular that `v` is never omitted for thin names.
- **A8** Nothing in the adapter reads a rate-limit, credit or quota header; cost is unmeasured by the pipeline.

---

## 5. Disagreement with public documentation

The public MarketData v1 stock-candles docs place the resolution in the **path** (`/v1/stocks/candles/{resolution}/{symbol}/`), which both callers do, and accept `from`/`to` as dates or timestamps — consistent with the repository. The repository additionally sends `adjustsplits=true` and `extended`. Where any conflict arises, **the repository code is authoritative for this preflight** because it is what will run; the probes below replicate §1.2 exactly.
