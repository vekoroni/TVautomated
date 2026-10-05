"""Backfill completed regular-session 5-minute stock bars from Polygon into the canonical intraday store.

Step 4 (ACK, 4 Oct 2026, option b): intraday BEH-001 evidence needs history before the 18 recorded sessions
(4 Sep - 2 Oct 2026). Polygon supplies stock bars only; options data stays MarketData-only.

Reuses the existing owner: canonical_data.intraday_bars.CanonicalMinuteBarResolver writes each ticker-session as a
hash-checked canonical INTRADAY_BAR record (bulk path: one transaction and one request-ledger row per
ticker fetch, ACK 4 Oct 2026). Tickers are registered in this backfill's
own run lifecycle with the INTRADAY_BAR capability only. Extended-hours bars never enter. Sessions already stored
are skipped, so the command is resumable. --plan-only makes no provider call and writes nothing.

Run manually from PowerShell (never while a Phantom backfill is writing), for example:
    python scripts\\backfill_polygon_intraday.py --plan-only
    python scripts\\backfill_polygon_intraday.py
The API key is read from POLYGON_API_KEY (environment or the project .env) and is never printed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Iterable, Mapping
from urllib.parse import quote

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import CanonicalFeatureFlags, CanonicalRegistry, DatasetType  # noqa: E402
from canonical_data.session_clock import is_xnys_session, session_bounds  # noqa: E402

PROVIDER = "POLYGON"
STAGE = "INTRADAY_HISTORY_BACKFILL"
INTERVAL_MINUTES = 5
ADJUSTMENT = "SPLIT_ADJUSTED"          # Polygon adjusted=true; matches the completed-profile records
BASE_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/5/minute/{start}/{end}"
CHUNK_DAYS = 120                        # ~84 sessions x up to 192 bars with extended hours < Polygon's 50,000 limit
REGISTRY = ROOT / "data" / "canonical" / "control_plane.sqlite"
PAYLOADS = ROOT / "data" / "canonical" / "payloads"
DEFAULT_UNIVERSE = ROOT / "data" / "universe" / "polygon_liquid_universe.csv"
DEFAULT_START = date(2024, 9, 3)
DEFAULT_END = date(2026, 9, 3)          # the day before the recorded 5-minute coverage begins


def xnys_sessions(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if is_xnys_session(day):
            days.append(day)
        day += timedelta(days=1)
    return days


def split_regular_sessions(raw: pd.DataFrame) -> dict[date, pd.DataFrame]:
    """Polygon aggregate rows (t ms epoch, o/h/l/c/v/vw/n) -> regular-session frames keyed by session date."""
    if raw is None or raw.empty:
        return {}
    frame = raw.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
                                "vw": "vwap_provider", "n": "trade_count"}).copy()
    frame["timestamp_utc"] = pd.to_datetime(frame.pop("t"), unit="ms", utc=True)
    frame["_session"] = frame["timestamp_utc"].dt.tz_convert("America/New_York").dt.date
    out: dict[date, pd.DataFrame] = {}
    for session, group in frame.groupby("_session"):
        if not is_xnys_session(session):
            continue
        open_utc, close_utc = session_bounds(session)
        regular = group[(group["timestamp_utc"] >= open_utc) & (group["timestamp_utc"] < close_utc)]
        if not regular.empty:
            out[session] = regular.drop(columns="_session").sort_values("timestamp_utc").reset_index(drop=True)
    return out


def missing_sessions(wanted: Iterable[date], *, stored: set[date]) -> list[date]:
    return [d for d in wanted if d not in stored]


def estimate_plan(*, tickers: list[str], sessions: list[date], stored: Mapping[str, set[date]]) -> dict:
    to_fetch = {t: missing_sessions(sessions, stored=stored.get(t, set())) for t in tickers}
    need = {t: days for t, days in to_fetch.items() if days}
    requests = sum(max(1, -(-((days[-1] - days[0]).days + 1) // CHUNK_DAYS)) for days in need.values())
    count = sum(len(days) for days in to_fetch.values())
    return {"tickers": len(tickers), "sessions_in_range": len(sessions), "sessions_wanted": len(tickers) * len(sessions),
            "sessions_already_stored": len(tickers) * len(sessions) - count, "sessions_to_fetch": count,
            "tickers_needing_fetch": len(need), "provider_requests_estimate": requests,
            "storage_estimate_gb": round(count * 7.5 / 1024 / 1024, 1)}   # ~7.5 KB per 78-bar parquet session


def stored_sessions(registry: CanonicalRegistry, tickers: Iterable[str], start: date, end: date) -> dict[str, set[date]]:
    wanted = {t.upper() for t in tickers}
    out: dict[str, set[date]] = {}
    for r in registry.list_dataset_records(DatasetType.INTRADAY_BAR):
        extra = dict(r.scope.extra) if not isinstance(r.scope.extra, dict) else r.scope.extra
        if (r.instrument_id in wanted and extra.get("interval") == f"{INTERVAL_MINUTES}min"
                and extra.get("session_segment") == "REGULAR" and start <= r.session_date <= end):
            # COMPLETE or PARTIAL: a thin name's partial session (bars with no trades) is stored, not missing.
            out.setdefault(r.instrument_id, set()).add(r.session_date)
    return out


def fetched_tickers(run_id: str) -> set[str]:
    """Tickers whose Polygon fetch this backfill run already finished (one ledger row per ticker fetch)."""
    import sqlite3
    if not Path(REGISTRY).exists():
        return set()
    with sqlite3.connect(f"file:{Path(REGISTRY).as_posix()}?mode=ro", uri=True, timeout=30) as connection:
        try:
            rows = connection.execute("SELECT DISTINCT ticker FROM api_request_ledger WHERE run_id = ? "
                                      "AND resolution = 'PROVIDER_FETCH'", (run_id,)).fetchall()
        except sqlite3.OperationalError:
            return set()
    return {str(r[0]).upper() for r in rows}


def shard_tickers(tickers: list[str], spec: str | None) -> list[str]:
    """--shard K/N: the K-th of N disjoint slices (by position), so N processes can split one backfill."""
    if not spec:
        return list(tickers)
    k, n = (int(x) for x in str(spec).split("/"))
    if not 1 <= k <= n:
        raise ValueError("--shard must be K/N with 1 <= K <= N")
    return [t for i, t in enumerate(tickers) if i % n == k - 1]


def fetch_polygon(ticker: str, start: date, end: date, api_key: str) -> pd.DataFrame:
    import requests
    frames, cursor = [], start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=CHUNK_DAYS - 1))
        response = None
        for attempt in range(5):
            response = requests.get(BASE_URL.format(ticker=quote(ticker, safe=""), start=cursor, end=stop),
                                    params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key},
                                    timeout=(10, 60))
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            time.sleep(min(60, 2 ** attempt * 2))
        response.raise_for_status()
        results = response.json().get("results") or []
        if results:
            frames.append(pd.DataFrame(results))
        cursor = stop + timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _tickers(args) -> list[str]:
    if args.tickers:
        names = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        table = pd.read_csv(args.universe)
        names = table.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        if args.include_scanner:
            from scripts.avshunter_universe_scanner import TIER2_UNIVERSE
            names += [t.upper() for t in TIER2_UNIVERSE]
    return list(dict.fromkeys(names))


def _register(lifecycle, run_id: str, ticker: str) -> None:
    if lifecycle.latest(run_id, ticker) is None:
        lifecycle.register(run_id, ticker, stage=STAGE, allowed_capabilities=(DatasetType.INTRADAY_BAR,))


def run(args) -> dict:
    tickers = shard_tickers(_tickers(args), getattr(args, "shard", None))
    sessions = xnys_sessions(args.start, args.end)
    run_id = f"intraday_backfill_{args.start:%Y%m%d}_{args.end:%Y%m%d}"
    registry = CanonicalRegistry(REGISTRY); registry.initialise()
    stored = stored_sessions(registry, tickers, args.start, args.end)
    # Resume (5 Oct 2026): a ticker this run already fetched is done - its unstored sessions had no bars.
    for ticker in fetched_tickers(run_id) & set(tickers):
        stored[ticker] = set(sessions)
    plan = estimate_plan(tickers=tickers, sessions=sessions, stored=stored)
    print(json.dumps({"mode": "PLAN_ONLY" if args.plan_only else "BACKFILL", "start": str(args.start),
                      "end": str(args.end), **plan}, indent=2))
    if args.plan_only:
        return plan
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is required (environment or .env); it is never printed")
    from canonical_data.intraday_bars import CanonicalMinuteBarResolver
    flags = CanonicalFeatureFlags(enabled=True, write_through=True, stage_gating_enforced=False,
                                  offline_replay=False, ohlcv_mode="ACTIVE")
    # The lifecycle references run_registry (pilot 4 Oct 2026: FOREIGN KEY constraint failed) - register the run first.
    registry.register_run(run_id, STAGE, args.end, metadata={"provider": PROVIDER, "interval_minutes": INTERVAL_MINUTES,
                                                             "start": str(args.start), "end": str(args.end)})
    resolver = CanonicalMinuteBarResolver(registry_path=REGISTRY, payload_root=PAYLOADS, run_id=run_id,
                                          requesting_stage=STAGE, flags=flags)
    todo = {t: missing_sessions(sessions, stored=stored.get(t, set())) for t in tickers}
    todo = {t: days for t, days in todo.items() if days}
    counts = {"tickers_done": 0, "sessions_written": 0, "sessions_no_bars": 0, "ticker_errors": 0}
    errors: list[dict] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_polygon, t, days[0], days[-1], api_key): t for t, days in todo.items()}
        for future in as_completed(futures):           # network in parallel; canonical writes on this thread only
            ticker = futures[future]
            try:
                by_session = split_regular_sessions(future.result())
                _register(resolver.lifecycle, run_id, ticker)
                wanted = {d: by_session[d] for d in todo[ticker] if d in by_session}
                counts["sessions_no_bars"] += len(todo[ticker]) - len(wanted)   # thin/halted/unlisted: stated
                span_days = (todo[ticker][-1] - todo[ticker][0]).days + 1
                # ACK 4 Oct 2026 (option a): one transaction and one ledger row per ticker fetch.
                records = resolver.persist_completed_sessions(
                    ticker=ticker, sessions=wanted, provider=PROVIDER, interval_minutes=INTERVAL_MINUTES,
                    adjustment_convention=ADJUSTMENT, physical_requests=max(1, -(-span_days // CHUNK_DAYS)))
                counts["sessions_written"] += len(records)
            except Exception as error:  # noqa: BLE001 - one ticker never stops the backfill; recorded
                counts["ticker_errors"] += 1
                errors.append({"ticker": ticker, "error": f"{type(error).__name__}: {str(error)[:200]}"})
            counts["tickers_done"] += 1
            if counts["tickers_done"] % 25 == 0:
                print(f"{counts['tickers_done']}/{len(todo)} tickers | {counts['sessions_written']} sessions | "
                      f"{counts['ticker_errors']} errors | {(time.time() - started) / 60:.0f} min", flush=True)
    shard = str(getattr(args, "shard", None) or "").replace("/", "of")
    receipt = ROOT / "Enhancements" / "outcomes" / "intraday_backfill" / (
        f"{run_id}{'_shard' + shard if shard else ''}_receipt.json")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"run_id": run_id, "plan": plan, "counts": counts, "errors": errors,
                                   "finished_utc": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    print(json.dumps({"counts": counts, "receipt": str(receipt)}, indent=2))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--tickers", help="Comma-separated tickers (default: the pipeline universe)")
    source.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--include-scanner", action=argparse.BooleanOptionalAction, default=True,
                        help="Also backfill the scanner's list (default on)")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--workers", type=int, default=4, help="Parallel Polygon fetches (writes stay single-threaded)")
    parser.add_argument("--plan-only", action="store_true", help="No provider call, no writes: counts and estimates")
    parser.add_argument("--shard", help="K/N: run the K-th of N disjoint ticker slices (run N processes to split work)")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be on or before --end")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
