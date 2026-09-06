# AVS-PRE-001 — MarketData stock-candle entitlement preflight: result

**Executed:** 2026-09-04 08:01–08:05 UTC (04:01–04:05 America/New_York)
**Session under test:** **2026-09-03** (Thursday) — derived, not hard-coded
**Requests made:** **22 of a 24 cap** (19 planned + 3 reserve, each reserve use justified below)
**Credits consumed:** 17 (1 per successful candle response, 0 per `no_data` 404)
**Outcome:** **D — PARTIAL**, on the letter of the §5 criterion. The *entitlement itself* is A-grade; the shortfall is one client-side defect plus one session-specific ticker gap. Both are quantified below.

---

## 0. Two things to read before anything else

**0.1 The session is 2026-09-03, not 2026-09-04.** The task text said "Friday 4 September 2026" but also said to derive it. Derivation wins, and it disagrees: the run started at **04:01 ET on Friday 4 September, five and a half hours before the 09:30 open**. Friday's session had not happened, so the last *completed* XNYS session was **Thursday 2026-09-03**. Probe **P4** confirms it empirically — requesting 2026-09-04 returns `404 {"s":"no_data"}`. Labor Day (2026-09-07) was correctly excluded from the calendar but is irrelevant at this run time.

**0.2 The headline is not the entitlement — it is a P0 defect in the adapter.** The plan serves everything the completed-profile stage needs. But `MarketDataStockCandleAdapter.fetch_range` encodes `from`/`to` as **UTC ISO-8601 with a `Z` suffix**, and the provider **ignores the offset and reads the wall-clock as America/New_York**. Requesting the session as `13:30Z → 20:00Z` (which *is* 09:30–16:00 ET) returns **13:30–15:55 ET — the last 2½ hours of the session, 30 bars of 78**, with `s="ok"`, no warning, and no error. Had the profile stage been enabled last night, it would have built every completed profile from the afternoon only and reported success.

---

## 1. Outcome: D — PARTIAL

§5's criterion for **A — FULL** is "5-min RTH candles for the completed session, **≥ 95 % coverage on all 10 tickers**, same-evening availability, volume present." Nine of ten tickers meet it once the window is expressed correctly; **EBC returns no data at all for 2026-09-03** and therefore scores 0 %. The "all 10" clause fails, so A cannot be claimed.

**D's own wording does not fit cleanly either**, and the report says so rather than forcing it: coverage is *not* < 95 % on liquid names (all six are 100 %), and thin names do *not* systematically fail (three of four thin names return complete frames). D is assigned because it is the only outcome that leaves AG-19 viable while recording a failure fraction against the systemic-failure threshold — which is exactly the situation.

**Observed failure fraction: 1/10 = 0.10**, against `AVSHUNTER_PROFILE_MAX_FAILURE_RATIO` default **0.05**. The point estimate trips the threshold. A 10-ticker sample cannot establish the true rate — one failure in ten has a 95 % confidence interval of roughly 0.3 %–45 % — so this must be re-measured on a larger sample before AG-19, not treated as a settled 10 %.

### Evidence rows that decide the outcome

| Row | Probe | Request | Result | What it decides |
|---|---|---|---|---|
| 1 | **P1** ×9 | 5-min, `extended=false`, `from=2026-09-03T13:30:00Z`, `to=…T20:00:00Z` | `s=ok`, **30 bars**, 13:30→15:55 **ET**, coverage **0.3846** | The adapter's own encoding yields 38.5 % coverage on every ticker |
| 2 | **R2** | identical, but `from=2026-09-03T09:30:00`, `to=…T16:00:00` (naked wall-clock) | `s=ok`, **78 bars**, 09:30→15:55 ET, coverage **1.0** | The entitlement is complete; the shortfall in row 1 is client-side |
| 3 | **P1** EBC | 5-min, session window | **HTTP 404** `{"s":"no_data",…}` | One of ten tickers has no data for this session |
| 4 | **R1** EBC | full correct wall-clock window | **HTTP 404** `no_data` | EBC's gap is not an artefact of the wrong window |
| 5 | **R3** EBC | same, but session 2026-08-06 | `s=ok`, **78 bars**, coverage **1.0** | EBC *is* inside the plan's universe — the gap is session-specific to 2026-09-03 |
| 6 | **P5** | `extended=true`, 04:00–20:00 ET | **144 bars**, 08:00→19:55 ET, 78 RTH + 66 extended, coverage 1.0 | Full session available; extended bars served but unlabelled |
| 7 | **P2** ×3 | SPY at 1, 15, 30 min | 150 / 10 / 5 bars, all `s=ok` | All four intervals served |
| 8 | **P4** | 5-min, **2026-09-04** (not yet opened) | **HTTP 404** `no_data` | No forward-dated data; confirms 09-03 is the completed session |

Rows 1 and 2 are the same ticker, same session, same interval, differing only in how the time window is spelled. That is the whole finding.

**What this means for AVS-SD-003:** AG-19 is viable *this week* on the entitlement. It is **not** viable until the encoding defect (§4 D1) is fixed, because the stage would otherwise succeed while producing afternoon-only profiles — a silent-wrong outcome strictly worse than the current fail-closed behaviour that AVS-RCA-002 documented.

---

## 2. The eight answers

**1 — Delay: same-evening.** Thursday 2026-09-03's complete 78-bar RTH session was served at 04:01 ET on Friday, about 12 hours after the 16:00 close, with no delay flag. *Evidence: R2 (78/78, coverage 1.0); P4 returns `no_data` for the not-yet-opened 2026-09-04, so nothing forward-dated is being served.*

**2 — Intervals served: all four — 1, 5, 15, 30.** *Evidence: P2 — 1-min 150 bars, 15-min 10, 30-min 5, all `s=ok`; P1 5-min. Each equals exactly 150 minutes, the span the misparsed window actually requested, so all four are served at full fidelity.* This matches `SUPPORTED_INTERVALS = (1, 5, 15, 30)`; no interval needs to be dropped from the cadence enum.

**3 — History depth: at least the completed session minus 20 trading days (2026-08-06), full frame.** *Evidence: R3 — EBC on 2026-08-06 returns 78/78 with coverage 1.0; P3 at −2 (2026-09-01), −5 (2026-08-27) and −20 (2026-08-06) all return complete frames for the span requested.* Nothing deeper was tested, so ≥20 sessions is a floor, not a limit.

**4 — Extended hours: returned, but NOT flagged.** *Evidence: P5 — `extended=true` over 04:00–20:00 ET returns 144 bars spanning 08:00→19:55 ET: 18 pre-market, 78 RTH, 48 post. Payload keys are exactly `c,h,l,o,s,t,v` — there is no session-segment field.* Segment can only be derived by clock arithmetic against `session_bounds`. The adapter's `session_segment` column is stamped from the *request* (`marketdata_stock_candles.py:78`), so it is an assertion the provider never corroborates.

**5 — No-data shape: HTTP 404 with body `{"s":"no_data","prevTime":null,"nextTime":null}`,** `Content-Length: 47`, `x-api-ratelimit-consumed: 0`. *Evidence: P6 (`ZZZZ`), P1 (`EBC`), R1 (`EBC`), P4 (future session) — four occurrences, byte-identical body.* Note it is a **404**, not a 200 — see §4 D2.

**6 — Cost: 1 credit per successful candle request, 0 per `no_data`.** 17 credits for 22 requests (18 successful, 4 no-data). Daily limit **100,000** (`x-api-ratelimit-limit`), remaining ~94,966 at the end, reset epoch 1788528600. A nightly completed-profile run of **1,601 tickers ≈ 1,601 credits = 1.6 % of the daily limit**. *Comfortably within quota, with ~60× headroom.* One 203 response (P1/AAPL) reported `consumed: 0`, suggesting an edge cache serves some repeats free, so 1,601 is an upper bound.

**7 — Timestamp convention: epoch **seconds**, UTC, aligned to bar **open**.** *Evidence: P1/SPY `t[0]=1788456600` → 2026-09-03T13:30:00Z = 09:30 ET; step exactly 300 s on every response; `gaps_vs_grid=0`; `duplicate_timestamps=0`; convention `EPOCH_S` on all 18 successful responses.* The adapter's magnitude heuristic (`ms` if `≥1e11`, else `s`) resolves correctly. **The conversion that actually matters is on the request side, not the response side:** `from`/`to` must be sent as naked America/New_York wall-clock. This is precisely where "cadence and gap detection go wrong if assumed" — the response side is fine and the request side is silently wrong.

**8 — Contradictions with the repository adapter: three, one of them P0.** Detailed in §4. In short: **(D1)** `from`/`to` are sent as UTC `…Z` but parsed as ET, truncating every completed session to its last 150 minutes; **(D2)** `no_data` arrives as HTTP 404, so `urlopen` raises before the adapter's `no_data` branch can run, making that branch dead code; **(D3)** the payload carries no session-segment marker, so the `session_segment` column is asserted rather than observed. Two further items are recording gaps rather than contradictions: **(D4)** the adapter reads no rate-limit headers, and **(D5)** it never inspects the HTTP status, so `203 Non-Authoritative Information` — returned on 15 of 18 successful responses — passes unnoticed.

---

## 3. Confirmed adapter assumptions

These were tested and hold. They need no work.

| Ref | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 | Timestamps are epoch seconds; `ms`/`s` inferred by magnitude | **CONFIRMED** | `EPOCH_S` on all 18 successful responses; `t[0]=1788456600` |
| A2 | Bar timestamps are bar-**open**, on the `expected_intraday_timestamps` grid | **CONFIRMED** | step 300 s exactly, `gaps_vs_grid=0`, first bar 09:30 ET in R2 |
| A5 | The 16:00 close bar is excluded (`inclusive_end = close − interval`) | **CONFIRMED** | R2 last bar 15:55 ET, 78 bars — matches the grid exactly |
| A7 | All six arrays always equal length; `v` never omitted, including thin names | **CONFIRMED** | `arrays_equal_length` true on all 18; volume present and non-zero on all, including RPRX/VIPS/CBSH |
| — | OHLC internally consistent (`low ≤ open,close ≤ high`) | **CONFIRMED** | `ohlc_inconsistent = 0` across every response; zero non-finite |
| — | No duplicate timestamps | **CONFIRMED** | `duplicate_timestamps = 0` across every response |

---

## 4. Defects to file against the adapter before AG-19

### D1 — P0: `from`/`to` are sent as UTC but parsed as America/New_York

`canonical_data\marketdata_stock_candles.py:135-137`

```python
"from": start_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
"to":   end_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
```

`build_completed_market_profiles.py:123` passes `session_bounds(session_date)` = 13:30Z–20:00Z for a normal session. The provider discards the `Z` and reads `13:30`–`20:00` as **Eastern**, then clips to RTH because `extended=false`, returning **13:30–15:55 ET**.

| Request form | Bars | Window returned | Coverage |
|---|---|---|---|
| `2026-09-03T13:30:00Z` → `T20:00:00Z` (adapter today) | 30 | 13:30–15:55 **ET** | **0.3846** |
| `2026-09-03T09:30:00` → `T16:00:00` (naked wall-clock) | **78** | 09:30–15:55 **ET** | **1.000** |

The failure is silent: `s="ok"`, arrays consistent, no gaps, no duplicates. `assess_intraday_quality` would compute `coverage = 30/78 = 0.385` and flag it — **if** anything gates on coverage. Nothing in `build_completed_market_profiles.py` does; it counts physical fetches and a failure ratio, not coverage. So the stage would emit 1,601 usable-looking `COMPLETED_SESSION` profiles whose POC, VAH and VAL describe only the afternoon.

**This is worse than the current state.** AVS-RCA-002 found the stage flagged off and Vanguard failing open with `INSUFFICIENT_DATA`. Enabling the stage with D1 unfixed would replace a visible failure with an invisible wrong answer.

**Fix:** send the session window as naked local wall-clock (`f"{session_date}T09:30:00"` / `T16:00:00`), or as bare dates per the legacy caller at `backfill_timeseries_into_packages.py:299-304`. Add a coverage assertion to the stage so a truncated frame cannot be published as `COMPLETED_SESSION`.

### D2 — P1: `no_data` is HTTP 404, so the adapter's `no_data` branch is unreachable

`parse_marketdata_stock_candles:46-48` returns an empty frame for `s ∈ {no_data, no data, nodata}`. But the provider returns **404** with that body, and `_request_json` (`:105-113`) uses `urllib.request.urlopen`, which **raises `HTTPError` on 404** before any parsing happens. The branch is dead code on the real transport.

Consequence: an unavailable ticker surfaces as an `HTTPError` inside the per-ticker loop, not as an empty frame. The resolver cannot distinguish `UNAVAILABLE_PROVIDER` from `INSUFFICIENT_DATA` — the exact classification P6 exists to establish — and the systemic-failure ratio counts a transport exception rather than a governed no-data state.

**Fix:** catch `HTTPError`, parse its body, and route `s="no_data"` into the existing empty-frame path with reason `NOT_YET_OBSERVABLE` (future session, as in P4) or `TICKER_INACTIVE` / `UNAVAILABLE_PROVIDER` (as in EBC). Both codes already exist in `DataExceptionReason`.

### D3 — P2: `session_segment` is asserted, never observed

The payload has no segment field (`c,h,l,o,s,t,v` only), yet `:78` stamps `session_segment` from the request. With `extended=true` (P5) the 144-bar frame mixes 18 pre-market, 78 RTH and 48 post-market bars with nothing to tell them apart. Any consumer trusting that column on an extended request is misled.

**Fix:** derive `session_segment` per bar by comparing its timestamp to `session_bounds(session_date)`, rather than copying the request parameter.

### D4 — P2: cost is unmeasured

The adapter reads no response headers. `x-api-ratelimit-limit`, `-remaining`, `-consumed` and `-reset` are present on every response and are exactly the per-request cost signal the request ledger needs for AVS-SD-003 G-08. *(This is the A8 gap from `00_endpoint_contract.md`, confirmed.)*

### D5 — P2: HTTP status is never inspected

`_request_json` accepts any 2xx. **15 of 18 successful responses were `203 Non-Authoritative Information`**, 3 were `200`. MarketData uses 203 to signal cached rather than freshly-computed data. The adapter checks only the `s` field, so this evidence-quality distinction is discarded. It should be recorded on the observation, not acted on — 203 responses here were complete and correct.

---

## 5. Method and compliance

- **No pipeline code was imported or executed.** The script imports only `json, os, pathlib, re, sys, time, urllib.*, datetime, zoneinfo` — verified by AST scan. The XNYS calendar and request shape were re-implemented from the contract in `00_endpoint_contract.md`, which was produced by reading `scripts\backfill_timeseries_into_packages.py`, `canonical_data\marketdata_stock_candles.py`, `canonical_data\intraday_bars.py`, `canonical_data\session_clock.py` and `scripts\build_completed_market_profiles.py` **as text**.
- **The API key was never printed, logged or written.** Loaded from the process environment (present, length recorded, value never surfaced); `.env.txt` was not read. Every logged URL and header passes through `redact()`, which masks the literal key, `token=…`, `Authorization:` and any `api_key` form. `01_responses.jsonl` stores `url_redacted` and `headers_redacted` only — the `Authorization` header is recorded as `Token <REDACTED>`.
- **Request cap respected.** The counter increments *before* each call and refuses at 24. 22 used, 2 unused.
- **One attempt per probe. No retries, no backoff.** Failures were recorded and the run moved on.
- **Writes confined to `audit\preflight\`.** The script refuses to run against any other destination (`:41-42`). Nothing under `data\`, the canonical store, the request ledger or any run directory was touched.

### Reserve usage — 3 of 5, each justified

The plan was 19; three reserve requests were used because P1 returned a genuinely ambiguous result that one request each could resolve.

| # | Probe | Why it was needed |
|---|---|---|
| 20 | **R1** EBC, correct wall-clock window | P1's EBC 404 was ambiguous: no data at all, or no data inside the misparsed 13:30–15:55 window? Answer: still `no_data`, so the gap is real. |
| 21 | **R2** SPY, correct wall-clock window | Every RTH probe returned exactly 150 minutes at every interval — consistent with a timezone misparse but not proof. R2 confirmed it and simultaneously established that full 78/78 coverage is available. This single request is what turned the outcome from "coverage is bad" into "the request is wrong". |
| 22 | **R3** EBC on 2026-08-06 | Distinguishes "EBC is outside the plan's universe" (would make thin-name failure structural) from "EBC has no data for this session" (a one-off). Answer: 78/78 on the older session, so EBC is covered and the 09-03 gap is session-specific. |

### Ticker selection — a deviation forced by a known defect

§3 says to pick the four thinnest names by `contract_bid_size` from `data\output\runs\20260904_004338\intelligence_lab\`. **Every `*bid_size` column in that directory is 0/256 non-null** — in both `final_opportunity_book` and `lab_triage_view`. That is gap **G-06** from AVS-RCA-002 (quote lineage dropped at the Lab boundary), reproduced here independently.

The field's producer was used instead: `options\options_intelligence_20260904_004338.csv`, restricted to the Lab's 256 tickers, where `contract_bid_size` is 241/256 non-null. 33 tickers tie at the minimum `0.0`, so ties were broken on `contract_ask_size` (lowest total displayed depth) rather than alphabetically, which is closer to the intent of "thinner names".

**Selected: `EBC` (ask 2), `RPRX` (5), `VIPS` (9), `CBSH` (10).** Full set: `SPY, AAPL, MSFT, NVDA, BAC, XLE, EBC, RPRX, VIPS, CBSH`.

### P4 deviation

§3's P4 specifies "today's session date if the run is on a trading day after close; **otherwise** the last completed session again with `to` set to the exact session close". The run is on a trading day but *before* the open, so the "otherwise" branch applies — and it is **byte-identical to P1/SPY**, which already requests exactly `session_bounds` open→close. It would have answered nothing.

P4 was instead pointed at **today's not-yet-opened session (2026-09-04)**, which does answer the delay question from the other side: the provider returns `404 no_data` for a session that has not happened, so nothing forward-dated is served and Thursday's completeness in R2 is genuine same-evening availability, not a stale roll-forward. The substitution is recorded in the probe's `note` field.

---

## 6. Deliverables

```
audit\preflight\marketdata_candle_preflight.py           the script (stdlib only)
audit\preflight\AVS-PRE-001_20260904_075820\
  00_endpoint_contract.md    what the repository's own code requests, and the 8 assumptions tested
  01_responses.jsonl         22 records, one per request, redacted
  02_quota_summary.json      credit headers, delta, per-request cost, 1,601-ticker extrapolation
  03_run_log.txt             redacted run log
  AVS-PRE-001_RESULT.md      this file
```
