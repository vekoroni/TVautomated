"""Intraday catch-up before Discovery (step 1 of the behavioural-stage design, F3 / F4; ACK approved 12 Oct 2026).

Root cause RC-I1 / RC-I6 (Enhancements/phase8/INTRADAY_COMPLETENESS_ROOT_CAUSE_20261012.md): five-minute sessions were
stored only by the Evening's market-profile stage, one session per run and after Discovery had already read them, so
Discovery read a morning snapshot or an older day, and sessions with no Evening after them were never stored.

This fills, before Discovery, every session in the behavioural reading window (the 60m swing window, 20 sessions by
config) that a ticker traded (daily volume > 0 in the canonical daily store) but whose stored pieces do not cover the
whole session (``canonical_data.intraday_bars.requested_covers_session``). The source is Polygon aggregates - the
approved second source for underlying bars (options stay MarketData only); MarketData stays the Evening profile
stage's source. Reuses the backfill's fetch and bulk store (scripts/backfill_polygon_intraday.py). A session with no
bars from Polygon either is stated (no trades / not served), never filled.

    python scripts\\intraday_catchup.py --plan-only      (no provider call, no writes: the gap list and counts)
    python scripts\\intraday_catchup.py                  (fetch and store; resumable - stored sessions are skipped)
    python scripts\\intraday_catchup.py --sessions 60    (one-off wider catch-up, ACK runs it)
The API key is read from POLYGON_API_KEY (environment or .env) and is never printed.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGE = "INTRADAY_CATCHUP"
REGISTRY = ROOT / "data" / "canonical" / "control_plane.sqlite"
PAYLOADS = ROOT / "data" / "canonical" / "payloads"
PRICES = ROOT / "data" / "canonical" / "historical_prices.sqlite"


def catchup_run_id(through: date) -> str:
    """One run per invocation (live 12 Oct 2026: a ticker registered under another stage in an earlier attempt must
    not block a rerun). Resumability comes from the store - whole sessions already stored are not gaps."""
    return f"intraday_catchup_{through:%Y%m%d}_{datetime.now(timezone.utc):%H%M%S}"


def _register_ticker(lifecycle, run_id: str, ticker: str) -> None:
    """Register the ticker under this stage - the stage the resolver writes with (live 12 Oct 2026: registering under
    the backfill's stage made every write STAGE_MISMATCH)."""
    from canonical_data import DatasetType
    if lifecycle.latest(run_id, ticker) is None:
        lifecycle.register(run_id, ticker, stage=STAGE, allowed_capabilities=(DatasetType.INTRADAY_BAR,))


def _safe_error(error: Exception) -> str:
    """Error text with any API key removed (an HTTP error can carry the request URL)."""
    import re
    return re.sub(r"(apiKey|api_key|token)=[^&\s]+", r"\g<1>=REDACTED", f"{type(error).__name__}: {error}")[:300]


def _policy() -> dict:
    cfg = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))
    return dict(cfg["intraday_completeness"])


def gap_sessions(tickers: Iterable[str], sessions: Iterable[date], *, stored: Mapping[str, Mapping[date, list]],
                 traded: Mapping[tuple, bool]) -> dict[str, list[date]]:
    """Per ticker, the sessions it traded whose stored pieces do not cover the whole session."""
    from canonical_data.intraday_bars import requested_covers_session
    out: dict[str, list[date]] = {}
    for ticker in tickers:
        have = stored.get(ticker, {})
        missing = [d for d in sessions if traded.get((ticker, d))
                   and not requested_covers_session(have.get(d, []), d)]
        if missing:
            out[ticker] = missing
    return out


def window_sessions(through: date, count: int) -> list[date]:
    from datetime import timedelta
    from canonical_data.session_clock import is_xnys_session
    days, day = [], through
    while len(days) < int(count):
        if is_xnys_session(day):
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def traded_sessions(sessions: list[date]) -> dict[tuple, bool]:
    marks = ",".join("?" * len(sessions))
    with contextlib.closing(sqlite3.connect(f"file:{PRICES.as_posix()}?mode=ro", uri=True)) as conn:
        rows = conn.execute(f"SELECT ticker, trading_date, volume FROM ohlcv_daily WHERE trading_date IN ({marks})",
                            [d.isoformat() for d in sessions]).fetchall()
    return {(str(t).upper(), date.fromisoformat(str(d)[:10])): bool(v and float(v) > 0) for t, d, v in rows}


def main(argv=None) -> int:
    from canonical_data.session_clock import session_snapshot
    policy = _policy()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--through", type=date.fromisoformat,
                        default=session_snapshot(datetime.now(timezone.utc)).last_completed_session)
    parser.add_argument("--sessions", type=int, default=int(policy["catchup_sessions"]))
    parser.add_argument("--workers", type=int, default=int(policy["catchup_workers"]))
    parser.add_argument("--tickers", help="Comma-separated tickers (default: every ticker that traded in the window)")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args(argv)

    from canonical_data import CanonicalFeatureFlags, CanonicalRegistry
    from canonical_data.intraday_bars import CanonicalMinuteBarResolver, CompletedIntradayIndex
    from scripts.backfill_polygon_intraday import (ADJUSTMENT, CHUNK_DAYS, INTERVAL_MINUTES, PROVIDER,
                                                   fetch_polygon, split_regular_sessions)
    sessions = window_sessions(args.through, args.sessions)
    traded = traded_sessions(sessions)
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()] if args.tickers
               else sorted({t for (t, d), v in traded.items() if v}))
    index = CompletedIntradayIndex.from_registry(REGISTRY)
    stored = {t: {date.fromisoformat(k): v for k, v in index.entries_for(t).items()} for t in tickers}
    todo = gap_sessions(tickers, sessions, stored=stored, traded=traded)
    plan = {"mode": "PLAN_ONLY" if args.plan_only else "CATCHUP", "through": args.through.isoformat(),
            "sessions": len(sessions), "first_session": sessions[0].isoformat(), "tickers_traded": len(tickers),
            "tickers_with_gaps": len(todo), "ticker_sessions_to_fetch": sum(len(v) for v in todo.values()),
            "gaps_by_session": {d.isoformat(): sum(d in v for v in todo.values()) for d in sessions}}
    print(json.dumps(plan, indent=2), flush=True)
    if args.plan_only or not todo:
        return 0
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is required (environment or .env); it is never printed")
    run_id = catchup_run_id(args.through)
    registry = CanonicalRegistry(REGISTRY); registry.initialise()
    try:
        registry.register_run(run_id, STAGE, args.through, metadata={"provider": PROVIDER, "sessions": len(sessions)})
    except Exception:  # noqa: BLE001 - already registered by an earlier catch-up for the same session
        pass
    flags = CanonicalFeatureFlags(enabled=True, write_through=True, stage_gating_enforced=False,
                                  offline_replay=False, ohlcv_mode="ACTIVE")
    resolver = CanonicalMinuteBarResolver(registry_path=REGISTRY, payload_root=PAYLOADS, run_id=run_id,
                                          requesting_stage=STAGE, flags=flags)
    counts = {"tickers_done": 0, "sessions_written": 0, "sessions_no_bars": 0, "ticker_errors": 0}
    errors: list[dict] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_polygon, t, days[0], days[-1], api_key): t for t, days in todo.items()}
        for future in as_completed(futures):            # network in parallel; canonical writes on this thread only
            ticker = futures[future]
            try:
                by_session = split_regular_sessions(future.result())
                _register_ticker(resolver.lifecycle, run_id, ticker)
                wanted = {d: by_session[d] for d in todo[ticker] if d in by_session}
                counts["sessions_no_bars"] += len(todo[ticker]) - len(wanted)
                span_days = (todo[ticker][-1] - todo[ticker][0]).days + 1
                records = resolver.persist_completed_sessions(
                    ticker=ticker, sessions=wanted, provider=PROVIDER, interval_minutes=INTERVAL_MINUTES,
                    adjustment_convention=ADJUSTMENT, physical_requests=max(1, -(-span_days // CHUNK_DAYS)))
                counts["sessions_written"] += len(records)
            except Exception as error:  # noqa: BLE001 - one ticker never stops the catch-up; recorded
                counts["ticker_errors"] += 1
                errors.append({"ticker": ticker, "error": _safe_error(error)})
                if counts["ticker_errors"] == 1:
                    print(f"first error ({ticker}): {errors[0]['error']}", flush=True)
            counts["tickers_done"] += 1
            if counts["tickers_done"] == 20 and counts["ticker_errors"] == 20:
                # Live 12 Oct 2026: 1,250 tickers failed in silence. Twenty failures in twenty is systemic - stop.
                for pending in futures:
                    pending.cancel()
                print("STOPPED: the first 20 tickers all failed - see the first error above", flush=True)
                break
            if counts["tickers_done"] % 250 == 0:
                print(f"{counts['tickers_done']}/{len(todo)} tickers | {counts['sessions_written']} sessions | "
                      f"{counts['ticker_errors']} errors | {(time.time() - started) / 60:.0f} min", flush=True)
    receipt = ROOT / "data" / "output" / "qa" / f"intraday_catchup_{args.through:%Y%m%d}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"run_id": run_id, "plan": plan, "counts": counts, "errors": errors[:200],
                                   "minutes": round((time.time() - started) / 60, 1),
                                   "finished_utc": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    print(json.dumps({"counts": counts, "receipt": str(receipt)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
