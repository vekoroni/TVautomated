r"""AVS-PRE-001 — MarketData stock-candle entitlement preflight.

Talks to MarketData directly with urllib so it measures the ENTITLEMENT, not the
adapter. It deliberately imports nothing from the pipeline: not
intelligent_orchestrator, morning_gate, any stage module, canonical_data,
market_structure, or the MarketData adapters. The XNYS calendar and the request
shape below are re-implemented here from the contract recorded in
00_endpoint_contract.md.

Safety properties:
  * MARKETDATA_API_KEY is read from the process environment or .env and is never
    printed, logged or written. Every logged URL and header is redacted.
  * Hard cap of MAX_REQUESTS HTTP requests, counted BEFORE each call.
  * One attempt per probe. No retry or backoff loops.
  * Writes only inside the result directory passed on the command line.

Usage: marketdata_candle_preflight.py <result_dir>
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
MAX_REQUESTS = 24
TIMEOUT_SECONDS = 20
BASE = "https://api.marketdata.app/v1/stocks/candles"

RESULT_DIR = pathlib.Path(sys.argv[1]).resolve()
REPO = pathlib.Path(__file__).resolve().parents[2]
if not str(RESULT_DIR).startswith(str(REPO / "audit" / "preflight")):
    raise SystemExit("refusing to write outside audit/preflight/")
RESULT_DIR.mkdir(parents=True, exist_ok=True)

RESPONSES = RESULT_DIR / "01_responses.jsonl"
LOG = RESULT_DIR / "03_run_log.txt"
_RESERVE = "--reserve" in sys.argv
_RESERVE2 = "--reserve2" in sys.argv
_log_fh = LOG.open("a" if (_RESERVE or _RESERVE2) else "w", encoding="utf-8")

# --------------------------------------------------------------------------
# Redaction — applied to every string that leaves this process
# --------------------------------------------------------------------------
_SECRETS: list[str] = []


def redact(text: str) -> str:
    out = str(text)
    for secret in _SECRETS:
        if secret:
            out = out.replace(secret, "<REDACTED>")
    out = re.sub(r"(?i)(token=)[^&\s\"']+", r"\1<REDACTED>", out)
    out = re.sub(r"(?i)(Authorization\"?\s*[:=]\s*\"?)(Token\s+)?[^\s\"',}]+",
                 r"\1<REDACTED>", out)
    out = re.sub(r"(?i)\bapi[_-]?key\b\s*[:=]\s*\S+", "api_key=<REDACTED>", out)
    return out


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {redact(msg)}"
    print(line, flush=True)
    _log_fh.write(line + "\n")
    _log_fh.flush()


# --------------------------------------------------------------------------
# Key loading — value never surfaces
# --------------------------------------------------------------------------
def load_api_key() -> str:
    key = (os.environ.get("MARKETDATA_API_KEY") or "").strip()
    source = "process environment"
    if not key:
        env_path = REPO / ".env"
        if not env_path.exists():
            raise SystemExit("MARKETDATA_API_KEY not set and .env not found — stopping")
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip().lstrip("﻿")
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            if name.strip() == "MARKETDATA_API_KEY":
                key = value.strip().strip('"').strip("'")
                source = ".env"
                break
    if not key:
        raise SystemExit("MARKETDATA_API_KEY missing — stopping (never reading .env.txt)")
    _SECRETS.append(key)
    log(f"API key loaded from {source}: present, length {len(key)} (value never logged)")
    return key


# --------------------------------------------------------------------------
# XNYS calendar — re-implemented, mirrors canonical_data/session_clock.py
# --------------------------------------------------------------------------
def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lval = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * lval) // 433
    month = (h + lval - 7 * m + 90) // 25
    day = (h + lval - 7 * m + 33 * month + 19) % 32
    return date(year, month, day)


def xnys_holidays(year: int) -> frozenset[date]:
    hs = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        hs.add(_observed(date(year, 6, 19)))
    nxt = _observed(date(year + 1, 1, 1))
    if nxt.year == year:
        hs.add(nxt)
    return frozenset(hs)


def is_xnys_session(d: date) -> bool:
    return d.weekday() < 5 and d not in xnys_holidays(d.year)


def is_early_close(d: date) -> bool:
    if not is_xnys_session(d):
        return False
    if d == _nth_weekday(d.year, 11, 3, 4) + timedelta(days=1):
        return True
    return d.month == 12 and d.day == 24


def previous_xnys_session(d: date) -> date:
    c = d - timedelta(days=1)
    while not is_xnys_session(c):
        c -= timedelta(days=1)
    return c


def sessions_back(d: date, n: int) -> date:
    c = d
    for _ in range(n):
        c = previous_xnys_session(c)
    return c


def session_bounds(d: date) -> tuple[datetime, datetime]:
    o = datetime.combine(d, dtime(9, 30), NEW_YORK)
    c = datetime.combine(d, dtime(13 if is_early_close(d) else 16, 0), NEW_YORK)
    return o.astimezone(timezone.utc), c.astimezone(timezone.utc)


def last_completed_session(now_utc: datetime) -> tuple[date, str]:
    local = now_utc.astimezone(NEW_YORK)
    today = local.date()
    if is_xnys_session(today):
        _, close_utc = session_bounds(today)
        if now_utc >= close_utc:
            return today, "today's session has closed"
        return previous_xnys_session(today), "today is a session but has not closed yet"
    return previous_xnys_session(today), "today is not an XNYS session"


def expected_rth_bars(d: date, interval: int) -> int:
    o, c = session_bounds(d)
    return int((c - o).total_seconds() // 60 // interval)


# --------------------------------------------------------------------------
# Request layer
# --------------------------------------------------------------------------
API_KEY = load_api_key()
_requests_made = 0
_responses: list[dict] = []


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def to_et(ts_utc: datetime) -> str:
    return ts_utc.astimezone(NEW_YORK).isoformat(timespec="seconds")


def parse_native_timestamps(values: list) -> tuple[list[datetime], str]:
    """Mirror the adapter's unit inference so the preflight tests the same assumption."""
    if not values:
        return [], "EMPTY"
    numeric = [v for v in values if isinstance(v, (int, float))]
    if len(numeric) == len(values):
        mag = max(abs(float(v)) for v in values)
        unit = "ms" if mag >= 10 ** 11 else "s"
        div = 1000.0 if unit == "ms" else 1.0
        return [datetime.fromtimestamp(float(v) / div, timezone.utc) for v in values], f"EPOCH_{unit.upper()}"
    out = []
    for v in values:
        try:
            out.append(datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc))
        except Exception:
            return [], "UNPARSEABLE"
    return out, "ISO_STRING"


def probe(pid: str, ticker: str, interval: int, start_utc: datetime, end_utc: datetime,
          session: date, extended: bool, note: str = "",
          literal_from: str | None = None, literal_to: str | None = None) -> dict:
    global _requests_made
    rec: dict = {
        "probe": pid, "ticker": ticker, "interval_minutes": interval,
        "session_date": session.isoformat(), "extended": extended, "note": note,
        "requested_from_utc": literal_from or iso_z(start_utc),
        "requested_to_utc": literal_to or iso_z(end_utc),
        "literal_params_used": bool(literal_from or literal_to),
        "requested_from_et": to_et(start_utc), "requested_to_et": to_et(end_utc),
    }
    if _requests_made + 1 > MAX_REQUESTS:
        rec["status"] = "SKIPPED_CAP"
        rec["error"] = f"would exceed cap of {MAX_REQUESTS}"
        log(f"[{pid}] {ticker} SKIPPED_CAP")
        _responses.append(rec)
        return rec

    params = {
        "from": literal_from or iso_z(start_utc),
        "to": literal_to or iso_z(end_utc),
        "extended": "true" if extended else "false",
        "adjustsplits": "true",
    }
    url = f"{BASE}/{interval}/{ticker.upper()}/"
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"Authorization": f"Token {API_KEY}", "Accept": "application/json"}
    rec["url_redacted"] = redact(request_url)
    rec["headers_redacted"] = {"Authorization": "Token <REDACTED>", "Accept": "application/json"}

    _requests_made += 1
    rec["request_number"] = _requests_made
    log(f"[{pid}] request {_requests_made}/{MAX_REQUESTS} {ticker} interval={interval} "
        f"extended={extended} {params['from']} -> {params['to']}")

    t0 = time.time()
    body_bytes = b""
    try:
        req = urllib.request.Request(request_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body_bytes = resp.read()
            rec["http_status"] = resp.status
            rec["response_headers"] = {k: redact(v) for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        body_bytes = e.read() or b""
        rec["http_status"] = e.code
        rec["response_headers"] = {k: redact(v) for k, v in (e.headers or {}).items()}
        rec["http_error"] = redact(str(e.reason))
    except Exception as e:                                    # one attempt, no retry
        rec["http_status"] = None
        rec["transport_error"] = redact(f"{type(e).__name__}: {e}")
    rec["latency_ms"] = round((time.time() - t0) * 1000, 1)
    rec["body_bytes"] = len(body_bytes)

    payload = None
    if body_bytes:
        try:
            payload = json.loads(body_bytes.decode("utf-8", errors="replace"))
        except Exception as e:
            rec["parse_error"] = redact(f"{type(e).__name__}: {e}")
    if rec.get("http_status") != 200 or payload is None:
        rec["body_first_2kb"] = redact(body_bytes[:2048].decode("utf-8", errors="replace"))

    if isinstance(payload, dict):
        rec["provider_status"] = payload.get("s")
        rec["payload_keys"] = sorted(payload.keys())
        t = list(payload.get("t") or [])
        o = list(payload.get("o") or [])
        h = list(payload.get("h") or [])
        low = list(payload.get("l") or [])
        c = list(payload.get("c") or [])
        v = list(payload.get("v") or [])
        rec["array_lengths"] = {"t": len(t), "o": len(o), "h": len(h), "l": len(low), "c": len(c), "v": len(v)}
        rec["arrays_equal_length"] = len({len(t), len(o), len(h), len(low), len(c), len(v)}) == 1
        rec["bar_count"] = len(t)
        stamps, convention = parse_native_timestamps(t)
        rec["timestamp_convention"] = convention
        if stamps:
            rec["native_first"] = t[0]
            rec["native_last"] = t[-1]
            rec["first_utc"] = iso_z(stamps[0])
            rec["last_utc"] = iso_z(stamps[-1])
            rec["first_et"] = to_et(stamps[0])
            rec["last_et"] = to_et(stamps[-1])
            rec["duplicate_timestamps"] = len(t) - len(set(t))
            deltas = sorted({int((stamps[i + 1] - stamps[i]).total_seconds())
                             for i in range(len(stamps) - 1)})
            rec["observed_step_seconds"] = deltas[:6]
            grid = interval * 60
            rec["gaps_vs_grid"] = sum(1 for i in range(len(stamps) - 1)
                                      if int((stamps[i + 1] - stamps[i]).total_seconds()) != grid)
            o_utc, c_utc = session_bounds(session)
            rec["bars_in_rth"] = sum(1 for s in stamps if o_utc <= s < c_utc)
            rec["bars_outside_rth"] = len(stamps) - rec["bars_in_rth"]
            rec["bars_before_open"] = sum(1 for s in stamps if s < o_utc)
            rec["bars_at_or_after_close"] = sum(1 for s in stamps if s >= c_utc)
            exp = expected_rth_bars(session, interval)
            rec["expected_bars"] = exp
            rec["coverage_ratio"] = round(rec["bars_in_rth"] / exp, 6) if exp else None
            rec["session_dates_seen_et"] = sorted({s.astimezone(NEW_YORK).date().isoformat() for s in stamps})
        if v:
            nz = [x for x in v if isinstance(x, (int, float)) and x > 0]
            rec["volume_present"] = True
            rec["volume_nonzero_count"] = len(nz)
            rec["volume_null_count"] = sum(1 for x in v if x is None)
        else:
            rec["volume_present"] = False
        if o and h and low and c:
            ok = bad = nonfinite = 0
            for i in range(min(len(o), len(h), len(low), len(c))):
                vals = (o[i], h[i], low[i], c[i])
                if any(x is None or not isinstance(x, (int, float)) for x in vals):
                    nonfinite += 1
                    continue
                if low[i] <= o[i] <= h[i] and low[i] <= c[i] <= h[i]:
                    ok += 1
                else:
                    bad += 1
            rec["ohlc_consistent"] = ok
            rec["ohlc_inconsistent"] = bad
            rec["ohlc_nonfinite"] = nonfinite
        for extra in ("updated", "observed_at", "nextTime", "prevTime"):
            if extra in payload:
                rec[f"payload_{extra}"] = payload[extra] if not isinstance(payload[extra], list) else \
                    {"len": len(payload[extra]), "first": payload[extra][:1]}

    log(f"[{pid}] {ticker} -> HTTP {rec.get('http_status')} s={rec.get('provider_status')} "
        f"bars={rec.get('bar_count')} coverage={rec.get('coverage_ratio')} "
        f"{rec.get('latency_ms')}ms")
    _responses.append(rec)
    return rec


def quota_headers(rec: dict | None) -> dict:
    if not rec:
        return {}
    hdrs = rec.get("response_headers") or {}
    keep = {}
    for k, val in hdrs.items():
        kl = k.lower()
        if any(tok in kl for tok in ("ratelimit", "rate-limit", "limit", "remaining",
                                     "reset", "credit", "quota", "retry-after", "consumed", "cost")):
            keep[k] = val
    return keep


# --------------------------------------------------------------------------
# Probe plan
# --------------------------------------------------------------------------
def main() -> int:
    now = datetime.now(timezone.utc)
    session, why = last_completed_session(now)
    o_utc, c_utc = session_bounds(session)
    today_et = now.astimezone(NEW_YORK).date()

    log(f"now_utc={iso_z(now)} now_et={to_et(now)} ({now.astimezone(NEW_YORK):%A})")
    log(f"derived last completed XNYS session = {session} ({why})")
    log(f"session bounds ET 09:30->{'13:00' if is_early_close(session) else '16:00'} "
        f"= {iso_z(o_utc)} -> {iso_z(c_utc)}")
    log(f"expected 5-min RTH bars for {session}: {expected_rth_bars(session, 5)}")

    thin = (REPO / "audit" / "preflight" / "_thin_tickers.txt").read_text(encoding="utf-8").split()
    tickers = ["SPY", "AAPL", "MSFT", "NVDA", "BAC", "XLE"] + thin
    log(f"ticker set ({len(tickers)}): {', '.join(tickers)}")

    first_rec = None

    # P1 — completed-session 5-minute candles, all 10
    for tk in tickers:
        r = probe("P1", tk, 5, o_utc, c_utc, session, extended=False,
                  note="completed-session RTH 5-min, exactly what build_completed_market_profiles requests")
        first_rec = first_rec or r

    # P2 — resolution sweep on SPY
    for iv in (1, 15, 30):
        probe("P2", "SPY", iv, o_utc, c_utc, session, extended=False,
              note="resolution sweep")

    # P3 — history depth
    for back in (2, 5, 20):
        d = sessions_back(session, back)
        so, sc = session_bounds(d)
        probe("P3", "SPY", 5, so, sc, d, extended=False,
              note=f"history depth: completed session minus {back} trading days")

    # P4 — delay check.
    # The prompt's "otherwise" branch (last completed session with to=exact close)
    # is byte-identical to P1/SPY, so it would answer nothing. Running against
    # TODAY's not-yet-opened session instead distinguishes "not yet observable"
    # from "delayed", which is the question P4 exists to answer.
    if is_xnys_session(today_et) and now < session_bounds(today_et)[1]:
        to_, tc_ = session_bounds(today_et)
        probe("P4", "SPY", 5, to_, tc_, today_et, extended=False,
              note="delay check against TODAY's session, which has not opened yet "
                   "(literal 'otherwise' branch would duplicate P1/SPY exactly)")
    else:
        probe("P4", "SPY", 5, o_utc, c_utc, session, extended=False,
              note="delay check, last completed session with to=exact close")

    # P5 — extended hours 04:00-20:00 ET
    ext_start = datetime.combine(session, dtime(4, 0), NEW_YORK).astimezone(timezone.utc)
    ext_end = datetime.combine(session, dtime(20, 0), NEW_YORK).astimezone(timezone.utc)
    probe("P5", "SPY", 5, ext_start, ext_end, session, extended=True,
          note="extended-hours window 04:00-20:00 ET, extended=true")

    # P6 — unknown ticker
    probe("P6", "ZZZZ", 5, o_utc, c_utc, session, extended=False,
          note="unknown/delisted symbol, no-data shape")

    last_rec = _responses[-1] if _responses else None

    with RESPONSES.open("w", encoding="utf-8") as fh:
        for r in _responses:
            fh.write(json.dumps(r, default=str) + "\n")

    before, after = quota_headers(first_rec), quota_headers(last_rec)
    delta = {}
    for k in set(before) | set(after):
        try:
            delta[k] = int(after.get(k, 0)) - int(before.get(k, 0))
        except (TypeError, ValueError):
            delta[k] = f"{before.get(k)} -> {after.get(k)}"
    made = _requests_made
    summary = {
        "generated_utc": iso_z(datetime.now(timezone.utc)),
        "session_under_test": session.isoformat(),
        "session_derivation": why,
        "requests_made": made,
        "request_cap": MAX_REQUESTS,
        "quota_headers_first_response": before,
        "quota_headers_last_response": after,
        "delta": delta,
        "all_header_names_seen": sorted({k for r in _responses for k in (r.get("response_headers") or {})}),
        "extrapolation_note": (
            "per-request cost = delta/requests_made; nightly cost for 1,601 tickers "
            "= per-request cost x 1601 (one 5-min completed-session call per ticker)"
        ),
    }
    for k, val in delta.items():
        if isinstance(val, int) and val and made:
            per = abs(val) / made
            summary.setdefault("extrapolated", {})[k] = {
                "per_request": round(per, 4),
                "for_1601_tickers": round(per * 1601, 1),
            }
    (RESULT_DIR / "02_quota_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    log(f"DONE requests_made={made}/{MAX_REQUESTS}")
    log(f"session_under_test={session.isoformat()}")
    _log_fh.close()
    print(json.dumps({"session": session.isoformat(), "requests_made": made,
                      "responses": len(_responses)}, indent=1))
    return 0


def reserve() -> int:
    """Two reserve requests to resolve a genuinely ambiguous P1/P6 result.

    Recorded reason: every RTH probe returned exactly 150 minutes of bars
    starting at 13:30 ET, i.e. the provider parsed the wall-clock part of the
    ISO-8601 "...Z" instant as America/New_York and discarded the offset. That
    makes EBC's 404 ambiguous: no data at all, or no data in the (wrong)
    13:30-15:55 ET window? R1 re-requests EBC over the true session expressed
    as naked local wall-clock; R2 confirms the interpretation on SPY.
    """
    global _requests_made, _responses
    existing = [json.loads(l) for l in RESPONSES.read_text(encoding="utf-8").splitlines() if l.strip()]
    _requests_made = sum(1 for r in existing if r.get("request_number"))
    _responses = list(existing)
    log(f"RESERVE start: {_requests_made} requests already made, cap {MAX_REQUESTS}")

    session = date.fromisoformat(existing[0]["session_date"])
    o_utc, c_utc = session_bounds(session)
    lf, lt = f"{session}T09:30:00", f"{session}T16:00:00"

    probe("R1", "EBC", 5, o_utc, c_utc, session, extended=False,
          literal_from=lf, literal_to=lt,
          note="RESERVE: does EBC have candles at all when the window is expressed as "
               "naked local wall-clock 09:30-16:00 ET? Disambiguates the P1 404.")
    probe("R2", "SPY", 5, o_utc, c_utc, session, extended=False,
          literal_from=lf, literal_to=lt,
          note="RESERVE: confirms the provider parses naked wall-clock as ET and returns "
               "the full 78-bar session, proving the Z-suffix misparse in P1.")

    with RESPONSES.open("w", encoding="utf-8") as fh:
        for r in _responses:
            fh.write(json.dumps(r, default=str) + chr(10))
    log(f"RESERVE done requests_made={_requests_made}/{MAX_REQUESTS}")
    _log_fh.close()
    print(json.dumps({"requests_made": _requests_made, "responses": len(_responses)}, indent=1))
    return 0


def reserve2() -> int:
    """One further reserve request. Reason: EBC returned no_data for the full
    correct session (R1), while the other three thin names returned data. This
    distinguishes "EBC is outside the plan's stock-candle universe" from "EBC
    has no data for this particular session"."""
    global _requests_made, _responses
    existing = [json.loads(l) for l in RESPONSES.read_text(encoding="utf-8").splitlines() if l.strip()]
    _requests_made = sum(1 for r in existing if r.get("request_number"))
    _responses = list(existing)
    log(f"RESERVE2 start: {_requests_made} requests already made, cap {MAX_REQUESTS}")
    d = date(2026, 8, 6)
    o_utc, c_utc = session_bounds(d)
    probe("R3", "EBC", 5, o_utc, c_utc, d, extended=False,
          literal_from=f"{d}T09:30:00", literal_to=f"{d}T16:00:00",
          note="RESERVE: EBC on an older session (completed-20), correct wall-clock window. "
               "Distinguishes never-covered from session-specific gap.")
    with RESPONSES.open("w", encoding="utf-8") as fh:
        for r in _responses:
            fh.write(json.dumps(r, default=str) + chr(10))
    log(f"RESERVE2 done requests_made={_requests_made}/{MAX_REQUESTS}")
    _log_fh.close()
    print(json.dumps({"requests_made": _requests_made}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(reserve2() if _RESERVE2 else (reserve() if _RESERVE else main()))
