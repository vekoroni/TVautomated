"""Governed writer of the board universe's daily bars into the pipeline price store (ACK 20 Nov 2026, option B).

Root cause (Enhancements/macro_board/STALE_UNIVERSE_PRICES_root_cause_2026-11-20.md): the store's only regular
writer is Discovery, whose universe became stock-only on 16 May 2026, so 37 board universe ETFs stopped on 15 May;
RSP and UUP were never in it and stopped on 20 Aug. The board covered this with its own grouped-bar fill, which
as-of builds skip and which never re-adjusts for splits.

This module is a separate step of Run-MacroInputs.ps1; the board build itself stays read-only on the store.
  - Daily (default): for each board universe ticker, the completed sessions the store lacks (after the board's
    settle margin) are inserted from the board's grouped daily bars (cached; a cached session costs no call).
    A stored value is never revised. A gap longer than ``max_daily_gap_sessions`` is left whole and reported for
    the backfill. One Polygon splits call covers the window: a listed split re-fetches that ticker's full adjusted
    history (old rows become recorded revisions); without the split check nothing is written; a day-on-day close
    ratio beyond ``jump_hold_ratio`` with no listed split is held, never written.
  - Backfill (one time, run by ACK): ``--backfill`` fetches each long-gap or never-stored ticker's adjusted daily
    history once and saves it with a review (a dry run, no store write); ``--execute DIR`` takes a SQLite backup
    and writes exactly the saved bars through HistoricalPriceDatabase.ingest.
Exit codes: 0 every ticker written or up to date; 2 something held, unavailable or left for the backfill (reason
in the receipt; the board is unaffected); 1 error. Keys never leave the transport.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
from typing import Callable, Iterable, Mapping, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT, HistoricalPriceDatabase  # noqa: E402
from macro_board import market_prices as mkt  # noqa: E402

DEFAULT_CONFIG = ROOT / "macro_board" / "config" / "board_store_writer_v1.json"
AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
SPLITS_URL = "https://api.polygon.io/v3/reference/splits"
PROVIDER = "POLYGON"
SOURCE_DAILY = "BOARD_UNIVERSE_DAILY"
SOURCE_SPLIT = "BOARD_UNIVERSE_SPLIT_REFETCH"
SOURCE_BACKFILL = "BOARD_UNIVERSE_BACKFILL"
Transport = Callable[[str, Mapping], tuple]
GroupedFetch = Callable[[date], "Mapping | None"]


# --- configuration -------------------------------------------------------------------------------------------

def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_config(path: Path = DEFAULT_CONFIG) -> tuple[dict, dict]:
    """(writer config with the board's settle margin, history start and price store added, board config)."""
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    board = json.loads(_resolve(cfg["board_config"]).read_text(encoding="utf-8"))
    cfg = {**cfg, "settle_minutes": float(board["prices"]["settle_minutes"]),
           "history_start": board["history_start"], "price_db": board["sources"]["price_db"]}
    return cfg, board


def board_universe(board_config: Mapping) -> list[str]:
    return sorted({t for group in board_config["universe"] for t in group["tickers"]})


def polygon_key() -> str:
    """POLYGON_API_KEY from the environment, else the repo .env (as the runner's producers do)."""
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("POLYGON_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def default_transport() -> Transport | None:
    key = polygon_key()
    if not key:
        return None
    import requests

    def transport(url, params):
        r = requests.get(url, params={**params, "apiKey": key}, timeout=60)
        ok = r.headers.get("content-type", "").startswith("application/json")
        return r.status_code, (r.json() if ok else {})
    return transport


# --- store reads ---------------------------------------------------------------------------------------------

def stored_state(db: HistoricalPriceDatabase, tickers: Sequence[str]) -> dict[str, dict]:
    """{ticker: {last, rows, last_close}} for complete bars; last None when the store never held the ticker."""
    out = {t: {"last": None, "rows": 0, "last_close": None} for t in tickers}
    if not tickers:
        return out
    marks = ",".join("?" for _ in tickers)
    with sqlite3.connect(f"file:{Path(db.database_path).as_posix()}?mode=ro", uri=True) as c:
        for t, n, last in c.execute(
                f"SELECT ticker, COUNT(*), MAX(trading_date) FROM ohlcv_daily WHERE adjustment_convention=? "
                f"AND bar_status='COMPLETE' AND ticker IN ({marks}) GROUP BY ticker", [DEFAULT_ADJUSTMENT, *tickers]):
            close = c.execute("SELECT close FROM ohlcv_daily WHERE ticker=? AND trading_date=? AND adjustment_convention=?",
                              [t, last, DEFAULT_ADJUSTMENT]).fetchone()
            out[t] = {"last": date.fromisoformat(last), "rows": int(n), "last_close": float(close[0])}
    return out


_FIELDS = ("open", "high", "low", "close", "volume")


def _stored_bars(db: HistoricalPriceDatabase, ticker: str) -> dict[str, tuple[float, ...]]:
    with sqlite3.connect(f"file:{Path(db.database_path).as_posix()}?mode=ro", uri=True) as c:
        return {d: tuple(float(x) for x in vals) for d, *vals in c.execute(
            "SELECT trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE ticker=? "
            "AND adjustment_convention=?", [ticker, DEFAULT_ADJUSTMENT])}


def _will_revise(stored: Sequence[float], incoming: Mapping) -> bool:
    """The store's own sameness rule (HistoricalPriceDatabase._same_price_row): any field beyond 1e-9 relative."""
    return any(abs(a - float(incoming[k])) > max(1e-8, abs(a) * 1e-9) for a, k in zip(stored, _FIELDS))


# --- plan ----------------------------------------------------------------------------------------------------

def plan_daily(state: Mapping[str, Mapping], *, last_completed: date, max_gap_sessions: int) -> dict[str, dict]:
    """Per ticker: UP_TO_DATE, GROUPED (the sessions to insert), GAP_TOO_LONG or NEVER_STORED (both: backfill)."""
    plan = {}
    for t, s in state.items():
        if s["last"] is None:
            plan[t] = {"action": "NEVER_STORED", "sessions": []}
            continue
        missing = mkt._sessions_between(s["last"], last_completed)
        if not missing:
            plan[t] = {"action": "UP_TO_DATE", "sessions": []}
        elif len(missing) > int(max_gap_sessions):
            plan[t] = {"action": "GAP_TOO_LONG", "sessions": [], "missing_sessions": len(missing),
                       "last_stored": s["last"].isoformat()}
        else:
            plan[t] = {"action": "GROUPED", "sessions": missing}
    return plan


# --- provider reads ------------------------------------------------------------------------------------------

def aggs_to_rows(results: Iterable[Mapping]) -> list[dict]:
    """Polygon daily aggregates -> store rows on their New York session date."""
    rows = []
    for r in results or []:
        if r.get("t") is None:
            continue
        day = pd.Timestamp(int(r["t"]), unit="ms", tz="UTC").tz_convert("America/New_York").date()
        rows.append({"date": day.isoformat(), "open": r.get("o"), "high": r.get("h"), "low": r.get("l"),
                     "close": r.get("c"), "volume": r.get("v")})
    return sorted(rows, key=lambda x: x["date"])


def fetch_aggs(ticker: str, start: str, end: str, transport: Transport) -> list[dict] | None:
    """The ticker's adjusted daily bars from ``start`` to ``end``; None when unavailable (never invented)."""
    try:
        status, payload = transport(AGGS_URL.format(ticker=ticker, start=start, end=end),
                                    {"adjusted": "true", "sort": "asc", "limit": 50000})
    except Exception:  # noqa: BLE001 - reported by the caller
        return None
    if status != 200:
        return None
    rows = aggs_to_rows((payload or {}).get("results") or [])
    return rows or None


def fetch_splits(start: date, end: date, transport: Transport) -> list[dict] | None:
    """Every US split executed in [start, end]; None when the check could not be made."""
    out, url, params = [], SPLITS_URL, {"execution_date.gte": start.isoformat(),
                                         "execution_date.lte": end.isoformat(), "limit": 1000}
    for _ in range(20):
        try:
            status, payload = transport(url, params)
        except Exception:  # noqa: BLE001
            return None
        if status != 200:
            return None
        out.extend((payload or {}).get("results") or [])
        url = (payload or {}).get("next_url")
        if not url:
            return out
        params = {}
    return None


def _max_jump(closes: Sequence[float]) -> float:
    """The largest day-on-day close ratio either way (2.0 for a doubling or a halving)."""
    worst = 1.0
    for a, b in zip(closes, closes[1:]):
        if a and b and a > 0 and b > 0:
            worst = max(worst, math.exp(abs(math.log(b / a))))
    return worst


# --- daily step ----------------------------------------------------------------------------------------------

def run_daily(db: HistoricalPriceDatabase, universe: Sequence[str], *, now: datetime, cfg: Mapping,
              transport: Transport | None, grouped_fetch: GroupedFetch, run_id: str | None = None) -> dict:
    last_completed = mkt.last_eligible_session(now, settle_minutes=float(cfg["settle_minutes"]))
    run_id = run_id or f"BOARD_STORE_DAILY_{now.strftime('%Y%m%dT%H%M%SZ')}"
    state = stored_state(db, list(universe))
    plan = plan_daily(state, last_completed=last_completed, max_gap_sessions=int(cfg["max_daily_gap_sessions"]))
    tickers: dict[str, dict] = {}
    for t, p in plan.items():
        if p["action"] == "UP_TO_DATE":
            tickers[t] = {"status": "UP_TO_DATE"}
        elif p["action"] in ("GAP_TOO_LONG", "NEVER_STORED"):
            tickers[t] = {"status": p["action"], "note": "left whole for the one-time backfill (--backfill)",
                          **{k: v for k, v in p.items() if k not in ("action", "sessions")}}
    todo = {t: p["sessions"] for t, p in plan.items() if p["action"] == "GROUPED"}
    splits = None
    if todo:
        window_start = min(s[0] for s in todo.values())
        splits = fetch_splits(window_start, last_completed, transport) if transport else None
    split_map: dict[str, list] = {}
    for s in splits or []:
        if s.get("ticker") in todo:
            split_map.setdefault(s["ticker"], []).append(
                {k: s.get(k) for k in ("execution_date", "split_from", "split_to")})
    grouped_cache: dict[date, Mapping | None] = {}
    hold_ratio = float(cfg["jump_hold_ratio"])
    db_written = False
    for t, sessions in sorted(todo.items()):
        days = [d.isoformat() for d in sessions]
        if splits is None:
            tickers[t] = {"status": "HELD", "reason": "SPLIT_CHECK_UNAVAILABLE", "sessions": days}
            continue
        if t in split_map:
            rows = fetch_aggs(t, cfg["history_start"], last_completed.isoformat(), transport)
            if not rows or rows[-1]["date"] != last_completed.isoformat():
                tickers[t] = {"status": "HELD", "reason": "SPLIT_REFETCH_UNAVAILABLE", "splits": split_map[t],
                              "sessions": days}
                continue
            res = db.ingest(t, rows, provider=PROVIDER, source_kind=SOURCE_SPLIT, source_run_id=run_id,
                            fetched_at=now)
            db_written = True
            tickers[t] = {"status": "SPLIT_REFETCHED", "splits": split_map[t], "batch_id": res.batch_id,
                          "inserted": res.inserted_rows, "revised": res.revised_rows,
                          "unchanged": res.unchanged_rows, "rejected": res.rejected_rows}
            continue
        rows, unavailable = [], []
        for d in sessions:
            if d not in grouped_cache:
                grouped_cache[d] = grouped_fetch(d)
            bar = (grouped_cache[d] or {}).get(t)
            if not bar or bar.get("c") is None:
                unavailable.append(d.isoformat())
                continue
            rows.append({"date": d.isoformat(), "open": bar.get("o"), "high": bar.get("h"), "low": bar.get("l"),
                         "close": bar.get("c"), "volume": bar.get("v")})
        if unavailable:
            tickers[t] = {"status": "HELD", "reason": "GROUPED_UNAVAILABLE", "unavailable": unavailable,
                          "sessions": days}
            continue
        jump = _max_jump([state[t]["last_close"], *[float(r["close"]) for r in rows]])
        if jump > hold_ratio:
            tickers[t] = {"status": "HELD", "reason": "UNEXPLAINED_JUMP", "max_jump_ratio": round(jump, 4),
                          "sessions": days, "note": "no split listed; check, then --refetch the ticker"}
            continue
        res = db.ingest(t, rows, provider=PROVIDER, source_kind=SOURCE_DAILY, source_run_id=run_id, fetched_at=now)
        db_written = True
        tickers[t] = {"status": "WRITTEN", "sessions": days, "batch_id": res.batch_id,
                      "inserted": res.inserted_rows, "revised": res.revised_rows, "unchanged": res.unchanged_rows}
    ok = {"UP_TO_DATE", "WRITTEN", "SPLIT_REFETCHED"}
    counts: dict[str, int] = {}
    for v in tickers.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    return {"run_id": run_id, "mode": "DAILY", "at_utc": now.astimezone(timezone.utc).isoformat(),
            "last_completed_session": last_completed.isoformat(), "db": str(db.database_path),
            "store_written": db_written, "splits_checked": splits is not None, "counts": counts,
            "exit_code": 0 if all(v["status"] in ok for v in tickers.values()) else 2,
            "tickers": dict(sorted(tickers.items()))}


def refetch(db: HistoricalPriceDatabase, tickers: Sequence[str], *, now: datetime, cfg: Mapping,
            transport: Transport) -> dict:
    """ACK-named tickers: re-fetch the full adjusted history (e.g. after a held UNEXPLAINED_JUMP is checked)."""
    last_completed = mkt.last_eligible_session(now, settle_minutes=float(cfg["settle_minutes"]))
    run_id = f"BOARD_STORE_REFETCH_{now.strftime('%Y%m%dT%H%M%SZ')}"
    out = {}
    for t in tickers:
        rows = fetch_aggs(t, cfg["history_start"], last_completed.isoformat(), transport)
        if not rows or rows[-1]["date"] != last_completed.isoformat():
            out[t] = {"status": "HELD", "reason": "REFETCH_UNAVAILABLE"}
            continue
        res = db.ingest(t, rows, provider=PROVIDER, source_kind=SOURCE_SPLIT, source_run_id=run_id, fetched_at=now)
        out[t] = {"status": "SPLIT_REFETCHED", "inserted": res.inserted_rows, "revised": res.revised_rows,
                  "unchanged": res.unchanged_rows}
    return {"run_id": run_id, "mode": "REFETCH", "tickers": out,
            "exit_code": 0 if all(v["status"] == "SPLIT_REFETCHED" for v in out.values()) else 2}


# --- one-time backfill ---------------------------------------------------------------------------------------

def backfill_dry_run(db: HistoricalPriceDatabase, universe: Sequence[str], *, now: datetime, cfg: Mapping,
                     transport: Transport, out_dir: Path, include: Sequence[str] = ()) -> dict:
    """Fetch once, save, review; no store write. Scope: long-gap and never-stored tickers plus ``include``."""
    last_completed = mkt.last_eligible_session(now, settle_minutes=float(cfg["settle_minutes"]))
    state = stored_state(db, list(universe))
    plan = plan_daily(state, last_completed=last_completed, max_gap_sessions=int(cfg["max_daily_gap_sessions"]))
    scope = sorted({t for t, p in plan.items() if p["action"] in ("GAP_TOO_LONG", "NEVER_STORED")} | set(include))
    out_dir = Path(out_dir)
    (out_dir / "fetched").mkdir(parents=True, exist_ok=True)
    tol, hold_ratio = float(cfg["seam_tolerance"]), float(cfg["jump_hold_ratio"])
    review: dict[str, dict] = {}
    for t in scope:
        rows = fetch_aggs(t, cfg["history_start"], last_completed.isoformat(), transport)
        if not rows:
            review[t] = {"status": "NOT_READY", "reasons": ["FETCH_UNAVAILABLE"]}
            continue
        (out_dir / "fetched" / f"{t}.json").write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
        stored = _stored_bars(db, t)
        overlap = [(stored[r["date"]], r) for r in rows if r["date"] in stored]
        moves = [abs(float(r["close"]) / s[3] - 1.0) for s, r in overlap if s[3] > 0]
        differs = [m for m in moves if m > tol]
        will_revise = sum(_will_revise(s, r) for s, r in overlap)
        jump = _max_jump([float(r["close"]) for r in rows])
        expected = mkt._sessions_between(date.fromisoformat(rows[0]["date"]), last_completed)
        have = {r["date"] for r in rows}
        holes = [d.isoformat() for d in expected if d.isoformat() not in have]
        reasons = []
        if rows[-1]["date"] != last_completed.isoformat():
            reasons.append("ENDS_BEFORE_LAST_SESSION")
        if jump > hold_ratio:
            reasons.append("INTERNAL_JUMP")
        review[t] = {"status": "NOT_READY" if reasons else "READY", "reasons": reasons, "rows": len(rows),
                     "first": rows[0]["date"], "last": rows[-1]["date"], "stored_rows": len(stored),
                     "stored_last": state[t]["last"].isoformat() if state[t]["last"] else None,
                     "overlap": len(overlap), "overlap_differs": len(differs), "will_revise": will_revise,
                     "overlap_max_abs_diff": round(max(differs), 6) if differs else 0.0,
                     "max_internal_jump_ratio": round(jump, 4), "missing_sessions_inside": len(holes),
                     "missing_sessions_sample": holes[:5]}
    payload = {"mode": "BACKFILL_DRY_RUN", "at_utc": now.astimezone(timezone.utc).isoformat(),
               "db": str(db.database_path), "last_completed_session": last_completed.isoformat(),
               "history_start": cfg["history_start"], "source_kind": SOURCE_BACKFILL,
               "provider_calls": len(scope), "marketdata_credits": 0,
               "rules": {"seam_tolerance": tol, "jump_hold_ratio": hold_ratio},
               "summary": {"scope": len(scope), "ready": sum(v["status"] == "READY" for v in review.values()),
                           "rows_fetched": sum(v.get("rows", 0) for v in review.values()),
                           "rows_that_will_revise": sum(v.get("will_revise", 0) for v in review.values()),
                           "closes_beyond_seam_tolerance": sum(v.get("overlap_differs", 0) for v in review.values())},
               "tickers": review}
    (out_dir / "review.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def backfill_execute(db: HistoricalPriceDatabase, out_dir: Path, *, backup_dir: Path,
                     accept: Sequence[str] = ()) -> dict:
    """Back up the store, then write exactly the reviewed READY bars (no new provider call).

    ``accept``: tickers ACK checked and releases whose only reason is INTERNAL_JUMP (a real market move in a
    leveraged ETF, e.g. SOXL +55% / SOXS -56% on 9 Apr 2025). Any other reason is never released."""
    out_dir = Path(out_dir)
    review = json.loads((out_dir / "review.json").read_text(encoding="utf-8"))
    if Path(review["db"]).resolve() != Path(db.database_path).resolve():
        raise ValueError(f"the review was made on {review['db']}, not {db.database_path}; nothing written")
    accepted = sorted(t for t in {a.upper() for a in accept}
                      if review["tickers"].get(t, {}).get("reasons") == ["INTERNAL_JUMP"])
    ready = [t for t, v in review["tickers"].items() if v["status"] == "READY" or t in accepted]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt = {"mode": "BACKFILL_EXECUTE", "at_utc": stamp, "review": str(out_dir / "review.json"),
               "db": str(db.database_path), "accepted_by_ack": accepted, "ingest": {}}
    if ready:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"historical_prices.pre_board_universe_backfill_{stamp}.sqlite"
        with sqlite3.connect(db.database_path) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
        receipt["backup"] = str(backup)
        fetched_at = datetime.fromisoformat(review["at_utc"])
        run_id = f"BOARD_UNIVERSE_BACKFILL_{out_dir.name}"
        for t in ready:
            rows = json.loads((out_dir / "fetched" / f"{t}.json").read_text(encoding="utf-8"))
            res = db.ingest(t, rows, provider=PROVIDER, source_kind=SOURCE_BACKFILL, source_run_id=run_id,
                            fetched_at=fetched_at)
            receipt["ingest"][t] = {"batch_id": res.batch_id, "inserted": res.inserted_rows,
                                    "revised": res.revised_rows, "unchanged": res.unchanged_rows,
                                    "rejected": res.rejected_rows}
    receipt["not_written"] = {t: v["reasons"] for t, v in review["tickers"].items() if t not in ready}
    (out_dir / f"execute_receipt_{stamp}.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    return receipt


# --- command line --------------------------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--db", help="price store (default: the board config's price_db)")
    ap.add_argument("--backfill", action="store_true", help="one-time backfill dry run: fetch, save, review; no write")
    ap.add_argument("--include", nargs="*", default=[], help="extra tickers for the backfill scope")
    ap.add_argument("--execute", metavar="DIR", help="write the READY bars saved by a backfill dry run in DIR")
    ap.add_argument("--accept", nargs="*", default=[], metavar="TICKER",
                    help="with --execute: release tickers held only for INTERNAL_JUMP after checking them")
    ap.add_argument("--refetch", nargs="+", metavar="TICKER", help="re-fetch these tickers' full adjusted history")
    a = ap.parse_args(argv)
    cfg, board = load_config(Path(a.config))
    db_path = Path(a.db) if a.db else _resolve(cfg["price_db"])
    if not db_path.is_file():
        print(f"[STOP] no price store at {db_path} (pass --db); nothing read or written")
        return 1
    db = HistoricalPriceDatabase(db_path)
    now = datetime.now(timezone.utc)
    if a.execute:
        receipt = backfill_execute(db, Path(a.execute), backup_dir=Path(db.database_path).parent / "backups",
                                   accept=a.accept)
        print(json.dumps({k: receipt[k] for k in ("backup", "accepted_by_ack", "not_written") if k in receipt}, indent=1))
        print(f"written: {len(receipt['ingest'])} tickers; receipt in {a.execute}")
        return 0 if not receipt["not_written"] else 2
    transport = default_transport()
    universe = board_universe(board)
    if a.backfill:
        if transport is None:
            print("[STOP] POLYGON_API_KEY not set; nothing fetched")
            return 1
        out_dir = _resolve(cfg["backfill_dir"]) / now.strftime("%Y%m%dT%H%M%SZ")
        review = backfill_dry_run(db, universe, now=now, cfg=cfg, transport=transport, out_dir=out_dir,
                                  include=[t.upper() for t in a.include])
        print(json.dumps(review["summary"], indent=1))
        for t, v in review["tickers"].items():
            if v["status"] != "READY":
                print(f"  NOT_READY {t}: {', '.join(v['reasons'])}")
        print(f"review: {out_dir / 'review.json'}\nto write it: python -m macro_board.store_writer --execute \"{out_dir}\"")
        return 0
    if a.refetch:
        if transport is None:
            print("[STOP] POLYGON_API_KEY not set; nothing fetched")
            return 1
        result = refetch(db, [t.upper() for t in a.refetch], now=now, cfg=cfg, transport=transport)
        print(json.dumps(result, indent=1))
        return result["exit_code"]
    grouped_dir = _resolve(cfg["grouped_cache_dir"])
    key = polygon_key() or None
    receipt = run_daily(db, universe, now=now, cfg=cfg, transport=transport,
                        grouped_fetch=lambda d: mkt.fetch_grouped_daily(d, cache_dir=grouped_dir, api_key=key))
    out = _resolve(cfg["daily_receipts_dir"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"store_writer_{receipt['last_completed_session']}_{now.strftime('%H%M%SZ')}.json"
    path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(f"session {receipt['last_completed_session']}: {receipt['counts']}  receipt: {path}")
    for t, v in receipt["tickers"].items():
        if v["status"] not in ("UP_TO_DATE", "WRITTEN", "SPLIT_REFETCHED"):
            print(f"  {v['status']} {t}: {v.get('reason', v.get('note', ''))}")
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
