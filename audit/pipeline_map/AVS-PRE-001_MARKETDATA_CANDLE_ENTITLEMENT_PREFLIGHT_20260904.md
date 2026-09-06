# AVS-PRE-001 — MarketData stock-candle entitlement preflight

**Issued:** 2026-09-04
**Agent:** Claude Code — writes **one** new script and **one** result directory; touches nothing else
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Interpreter:** `C:\Python314\python.exe`
**Script location:** `audit\preflight\marketdata_candle_preflight.py` (new; nothing under production paths)
**Result location:** `audit\preflight\AVS-PRE-001_<YYYYMMDD_HHMMSS>\`
**Hard request cap:** 24 HTTP requests total. The script must count them and refuse to exceed the cap.
**Why:** AVS-SD-002 §15.3 lists the MarketData candle entitlement, delay and credit behaviour as *explicitly unvalidated*. The completed-profile stage (AVS-SD-003 AG-19) depends on all three. Last night's run proved the **option-chain** entitlement (1,264 fetches) and said nothing about **stock candles** — the stage was flagged off and made zero candle requests. This preflight closes that gap in about twenty requests, against a closed market, so the result is a complete session rather than a partial one.

---

## 1. Constraints

- **Do not execute the pipeline.** Do not import `intelligent_orchestrator`, `morning_gate`, any stage module, `canonical_data\`, `market_structure\` or the MarketData adapter under `scripts\` or `canonical_data\`. This script talks to the provider directly with `requests` (or `urllib`), so that it measures the *entitlement*, not the adapter.
- **Read the key from `.env` without printing it.** Load `MARKETDATA_API_KEY` from `.env` in the repo root (or the process environment if already set). Never echo it, never write it to any output, never include it in a URL you log — redact `token=…` and `Authorization` from every logged request. If the key is missing, stop and report; do not look in `.env.txt`.
- **Do not write to the canonical data store, the request ledger, `data\`, or any run directory.** Results go only to the result directory above.
- **No retries that multiply requests.** One attempt per probe; on failure record the status and body (redacted) and move on. No backoff loops.
- **Respect the cap.** Increment a counter before every request; if the next request would exceed 24, skip it and record `SKIPPED_CAP`.
- **Timezone discipline.** All timestamps recorded in both the provider's native form and ISO-8601 UTC, plus the derived America/New_York wall-clock time. Never assume the provider returns local time.

## 2. Discover the correct endpoint first (0 requests)

Before any request, read the MarketData stock-candles endpoint contract from the repository's own adapter code — **read only, do not import** — to learn the URL shape, the interval parameter name and values, the date parameters, and any header the pipeline already uses. Look in:

- `scripts\backfill_timeseries_into_packages.py` (`marketdata_fetch_intraday_session`)
- the frame-preserving adapter added in AVS-SD-002 Phase 3 (search `canonical_data\` and `market_data\` for `candles`)
- `scripts\build_completed_market_profiles.py` for the interval and session the profile stage requests

Record what you found (endpoint, parameter names, the interval values the code uses, the expected bar count it derives) in `00_endpoint_contract.md`. The preflight must request **exactly what the profile stage will request**, so that the answer transfers.

If the repository code disagrees with the public MarketData docs you know, trust the repository code — that is what will run — and note the disagreement.

## 3. Probe set (≤ 24 requests)

**Session under test:** the last completed XNYS session as of run time. On Fri 4 Sep after close, Sat 5 or Sun 6 Sep that is **2026-09-04**. Mon 7 Sep is Labor Day; if the script runs Monday the completed session is still 2026-09-04. Derive it from the calendar, do not hard-code it; record it.

**Ticker set (10):** `SPY, AAPL, MSFT, NVDA, BAC, XLE` plus four thinner names taken from last night's Lab book — read `data\output\runs\20260904_004338\intelligence_lab\` (read-only) and pick the four tickers with the lowest `contract_bid_size` that are non-null. Record which four and why.

| # | Probe | Tickers | Interval | Session | Requests | Question answered |
|---|---|---|---|---|---|---|
| P1 | Completed-session five-minute candles | all 10 | 5 min | last completed | 10 | Does the plan serve 5-min stock candles for the completed session, for liquid and thin names alike? |
| P2 | Resolution sweep | SPY | 1, 15, 30 min | last completed | 3 | Which intervals are served? (needed for the cadence enum and expected-count logic) |
| P3 | History depth | SPY | 5 min | completed session minus 2, minus 5, minus 20 trading days | 3 | How far back can the profile stage fetch? (matters for `POC_slope_ATR` sequence features and for backfilling a warm cache) |
| P4 | Delay check | SPY | 5 min | **today's** session date if the run is on a trading day after close; otherwise the last completed session again with `to`/`end` set to the exact session close | 1 | Is the completed session available same-evening, or only one day delayed? |
| P5 | Extended-hours behaviour | SPY | 5 min | last completed, requesting the full 04:00–20:00 window | 1 | Does the plan return pre/post-market bars, and are they distinguishable from RTH? (the contract requires `session_segment`) |
| P6 | Unknown-ticker handling | `ZZZZ` (or a known delisted symbol) | 5 min | last completed | 1 | What does a no-data response look like? (the resolver must classify it as `UNAVAILABLE_PROVIDER` vs `INSUFFICIENT_DATA`) |
| P7 | Cost/rate headers | — | — | — | 0 | Captured from every response above |

Total: 19 requests, 5 in reserve. Do not use the reserve unless a probe returned an ambiguous result that one more request would resolve; if so, record why.

## 4. What to record per response

For every request, one JSON object in `01_responses.jsonl`:

- probe id, ticker, interval, requested session/date range
- redacted URL and redacted headers sent
- HTTP status, latency ms
- **every response header** (rate-limit, credits, quota, retry-after — names vary; capture all, redact nothing except the key)
- response body size; on non-200, the body (first 2 KB)
- parsed result: bar count; first and last timestamp (native, UTC, ET); whether `volume` is present and non-zero; whether OHLC are finite and internally consistent (`low ≤ open,close ≤ high`); count of duplicate timestamps; count of gaps versus the expected grid; bars outside 09:30–16:00 ET; the provider-reported session date if the payload carries one
- for P1 specifically, `expected_bars` for the interval (78 for 5-min on a full session; 26 for 15; 13 for 30; 390 for 1) and `coverage_ratio = bars_in_rth / expected_bars`

Also write `02_quota_summary.json`: the credit/quota headers before the first request and after the last, and the delta, so the per-ticker cost of a nightly run can be extrapolated (`delta / 19` and `× 1,601`).

## 5. Interpretation — write `AVS-PRE-001_RESULT.md`

State the entitlement outcome as **one** of these, with the evidence rows that decide it:

| Outcome | Meaning for AVS-SD-003 |
|---|---|
| **A — FULL** | 5-min RTH candles for the completed session, ≥ 95% coverage on all 10 tickers, same-evening availability, volume present. AG-19 is viable this week. |
| **B — DELAYED** | Candles are complete but for the session *before* the last completed one. The profile stage works, but AVS-SD-002 §6.1 requires the true source session to be labelled; AG-19 must verify that labelling. Note the delay in days. |
| **C — COARSE** | 5-min refused or truncated; 15- or 30-min served. The adapter's interval parameter handles it; expected counts change (26 / 13) and cadence must classify `FIFTEEN_MINUTE_TPO` / `THIRTY_MINUTE_TPO`. AG-19 viable with the interval set accordingly. |
| **D — PARTIAL** | Candles served but coverage < 95% on liquid names, or thin names systematically fail. Record which. AG-19 viable but the systemic-failure ratio (`AVSHUNTER_PROFILE_MAX_FAILURE_RATIO`, default 0.05) may trip — report the observed failure fraction against it. |
| **E — REFUSED** | Stock candles not served on this plan (401/403/402 or an entitlement message). The profile stage **cannot run**. AG-19 and cycle 2 wait on a plan change. The MVP is unaffected — cycle 1 fails Vanguard closed regardless. |

Then answer, in one line each, with the evidence row:

1. Delay: same-evening / T+1 / unknown.
2. Intervals served: which of 1 / 5 / 15 / 30.
3. History depth: the furthest-back session that returned a full frame.
4. Extended hours: returned / not returned / returned but not flagged.
5. No-data shape: status code and body pattern for P6.
6. Cost: credits per candle request, extrapolated cost for 1,601 tickers, and whether that fits the daily quota shown in the headers.
7. Timestamp convention: what the provider returns and what conversion the adapter must apply (this is where cadence and gap detection go wrong if assumed).
8. **Anything that contradicts what the repository adapter code assumes** (from `00_endpoint_contract.md`). Each such item is a defect to file against the adapter before AG-19, not something to work around here.

## 6. Deliverables

```
audit\preflight\marketdata_candle_preflight.py
audit\preflight\AVS-PRE-001_<timestamp>\
  00_endpoint_contract.md
  01_responses.jsonl
  02_quota_summary.json
  03_run_log.txt                 (redacted)
  AVS-PRE-001_RESULT.md
```

Finish by printing: the completed session used, the outcome letter (A–E), the total requests made (must be ≤ 24), and the one-line answers to §5 items 1–8.

Do not modify any file outside `audit\preflight\`. Do not proceed to any other AVS work in this session.
