"""M-G3-01 (Morning verification 20261008_220129; ACK approved 10 Oct 2026): the developing-profile stage is fast and
visible.

Root cause: Phase 5.4 widened the advisory market-structure worklist from the GO rows (35) to every adopted thesis
(about 2,300), and each ticker's 5-minute bars were fetched one after another inside the loop that also writes the
canonical registry; about 85 minutes with no progress line (gate 105 minutes in all).

Business rules:
- Provider fetches run in parallel within the existing live-fetch worker bound; registry writes and calculations stay
  sequential in the same order (SQLite ownership and evidence identity unchanged).
- The resolver receives exactly the provider response a direct fetch would return; it still filters to its own gap.
- A failed or missing prefetch falls back to the original live fetch (same error path), never to an empty frame.
- Progress is logged with counts and an estimated finish.
"""
from __future__ import annotations

import inspect
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import morning_gate  # noqa: E402

START = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


def test_fetches_run_in_parallel_within_the_bound_and_return_the_same_responses():
    live, peak, lock = [0], [0], threading.Lock()

    def fetch(ticker, start, end):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return f"BARS:{ticker}:{start.isoformat()}:{end.isoformat()}"

    tickers = [f"T{i}" for i in range(24)]
    cache = morning_gate._prefetch_minute_bars(tickers, START, END, fetch, workers=8)
    assert 1 < peak[0] <= 8
    assert cache == {t: f"BARS:{t}:{START.isoformat()}:{END.isoformat()}" for t in tickers}


def test_the_resolver_gets_the_prefetched_response_and_falls_back_to_a_live_fetch():
    calls = []

    def live_fetch(ticker, start, end):
        calls.append(ticker)
        return f"LIVE:{ticker}"

    cache = {"AAA": "PREFETCHED:AAA", "BBB": RuntimeError("timeout")}
    fetcher = morning_gate._prefetched_fetcher(cache, live_fetch, START, END)
    assert fetcher("AAA", START, END) == "PREFETCHED:AAA" and calls == []
    assert fetcher("BBB", START, END) == "LIVE:BBB"                     # a failed prefetch re-fetches live
    assert fetcher("CCC", START, END) == "LIVE:CCC"                     # not prefetched
    later = datetime(2026, 10, 9, 15, 30, tzinfo=timezone.utc)
    assert fetcher("AAA", START, later) == "LIVE:AAA"                   # a gap outside the prefetched range
    assert calls == ["BBB", "CCC", "AAA"]


def test_the_stage_uses_the_prefetch_and_logs_progress():
    src = inspect.getsource(morning_gate._enrich_msi_market_structure)
    assert "_prefetch_minute_bars(" in src and "_prefetched_fetcher(" in src
    assert "fetch_missing=_fetch_marketdata_five_minute_bars" not in src
    assert "MSI market structure progress" in src
