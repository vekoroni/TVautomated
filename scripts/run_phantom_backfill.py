"""PHANTOM five-year MarketData.app historical options backfill."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd
import requests

from phantom_database import PhantomDatabase, normalize_marketdata_chain, utc_now


MD_CHAIN_URL = "https://api.marketdata.app/v1/options/chain/{ticker}/"
INVALID_TICKERS = {
    "",
    "SYM",
    "SYMBOL",
    "TICKER",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",
    "NAN",
}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if ticker in INVALID_TICKERS:
        return ""
    if not TICKER_RE.match(ticker):
        return ""
    return ticker


def _last_weekday_on_or_before(value: date, weekday: int) -> date:
    current = value
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _latest_completed_date(include_today: bool) -> date:
    current = date.today()
    if not include_today:
        current -= timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _daterange_weekly(start: date, end: date, weekday: int) -> List[date]:
    current = _last_weekday_on_or_before(end, weekday)
    out = []
    while current >= start:
        out.append(current)
        current -= timedelta(days=7)
    return sorted(out)


def _prioritise_options_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_phantom_contract_priority"] = 0
    out["_phantom_score_priority"] = 0.0

    cols = {str(c).lower(): c for c in out.columns}
    for name in ("contract_dte", "selected_contract_dte", "dte"):
        if name in cols:
            numeric = pd.to_numeric(out[cols[name]], errors="coerce").fillna(0)
            out["_phantom_contract_priority"] += (numeric > 0).astype(int)
            break
    for name in ("contract_strike", "selected_contract_strike", "strike"):
        if name in cols:
            numeric = pd.to_numeric(out[cols[name]], errors="coerce").fillna(0)
            out["_phantom_contract_priority"] += (numeric > 0).astype(int)
            break
    for name in ("options_score", "oi_score", "composite_score", "ev_quality_score"):
        if name in cols:
            out["_phantom_score_priority"] = pd.to_numeric(out[cols[name]], errors="coerce").fillna(0)
            break

    return out.sort_values(
        ["_phantom_contract_priority", "_phantom_score_priority"],
        ascending=[False, False],
    )


def _load_tickers(repo_root: Path, run_id: str, tickers: str, max_tickers: int) -> List[str]:
    if tickers:
        values = [_clean_ticker(x) for x in tickers.replace(",", " ").split()]
        values = [x for x in values if x]
        return values[:max_tickers]
    candidates = [
        repo_root / "data" / "output" / "runs" / run_id / "options" / f"options_intelligence_{run_id}.csv",
        repo_root / "data" / "output" / "runs" / run_id / "superbrain" / f"eil_enriched_{run_id}.csv",
        repo_root / "data" / "output" / "runs" / run_id / "execution" / f"execution_v3_5_{run_id}.csv",
    ]
    seen = []
    for path in candidates:
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        cols = {str(c).lower(): c for c in df.columns}
        ticker_col = cols.get("ticker")
        if not ticker_col:
            continue
        if path.name.startswith("options_intelligence"):
            df = _prioritise_options_rows(df)
        for t in df[ticker_col].dropna().tolist():
            clean = _clean_ticker(t)
            if clean and clean not in seen:
                seen.append(clean)
            if len(seen) >= max_tickers:
                return seen
    return seen


def _query_key(ticker: str, quote_date: str, params: Dict[str, Any]) -> str:
    raw = json.dumps({"ticker": ticker, "date": quote_date, "params": params}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _estimated_credits(row_count: int) -> int:
    return max(1, int(math.ceil(max(1, row_count) / 1000.0)))


def fetch_chain(session: requests.Session, api_key: str, ticker: str, quote_date: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = MD_CHAIN_URL.format(ticker=ticker.upper())
    r = session.get(url, headers={"Authorization": f"Token {api_key}"}, params=params, timeout=45)
    if r.status_code == 429:
        time.sleep(30)
        r = session.get(url, headers={"Authorization": f"Token {api_key}"}, params=params, timeout=45)
    if not r.ok:
        # PHANTOM_NO_DATA_404_FIX: MarketData can return HTTP 404 with
        # a JSON body of {"s":"no_data"} for missing historical chains.
        # Treat that as permanent NO_DATA, not retryable ERROR.
        try:
            payload = r.json()
            if isinstance(payload, dict) and str(payload.get("s", "")).lower() == "no_data":
                payload.setdefault("errmsg", f"HTTP {r.status_code}: no_data")
                return payload
        except Exception:
            pass
        return {"s": "error", "errmsg": f"HTTP {r.status_code}: {r.text[:300]}"}
    return r.json()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build PHANTOM five-year historical options database.")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--run-id", default="")
    p.add_argument("--db-path", default="")
    p.add_argument("--end-date", default="", help="Last historical quote date to request, YYYY-MM-DD. Use this when the latest session is not yet published by MarketData.")
    p.add_argument("--data-lag-days", type=int, default=7, help="Safety lag for historical option-chain availability when --end-date is omitted.")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--max-tickers", type=int, default=200)
    p.add_argument("--tickers", default="")
    p.add_argument("--credit-cap", type=int, default=1200)
    p.add_argument("--strike-limit", type=int, default=40)
    p.add_argument("--min-open-interest", type=int, default=1)
    p.add_argument("--weekday", type=int, choices=[0, 1, 2, 3, 4], default=4, help="Historical weekly anchor: 0=Mon ... 4=Fri.")
    p.add_argument("--include-today", action="store_true", help="Allow today's date in the historical plan. Default uses completed sessions only.")
    p.add_argument("--max-no-data-streak", type=int, default=12, help="Stop a ticker after this many consecutive no-data historical dates.")
    p.add_argument("--sleep", type=float, default=0.15)
    p.add_argument("--execute", action="store_true", help="Actually call MarketData.app. Without this, prints the plan only.")
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repo_root = Path(args.repo_root)
    db_path = Path(args.db_path) if args.db_path else repo_root / "data" / "phantom" / "phantom_history.db"
    db = PhantomDatabase(db_path=db_path, repo_root=repo_root)
    if args.execute:
        db.initialise()

    run_id = args.run_id
    if not run_id:
        runs_dir = repo_root / "data" / "output" / "runs"
        dirs = sorted([p.name for p in runs_dir.iterdir() if p.is_dir() and p.name != "latest"], reverse=True)
        run_id = dirs[0] if dirs else ""
    tickers = _load_tickers(repo_root, run_id, args.tickers, args.max_tickers)
    if not tickers:
        raise SystemExit("No tickers found for PHANTOM backfill.")

    if getattr(args, "end_date", ""):
        end = date.fromisoformat(args.end_date)
    else:
        end = _latest_completed_date(bool(args.include_today)) - timedelta(days=max(0, int(getattr(args, "data_lag_days", 7))))
    start = end - timedelta(days=365 * int(args.years))
    quote_dates = _daterange_weekly(start, end, int(args.weekday))
    planned_queries = len(tickers) * len(quote_dates)
    print(json.dumps({
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "db_path": str(db_path),
        "run_id": run_id,
        "ticker_count": len(tickers),
        "sample_tickers": tickers[:10],
        "date_count": len(quote_dates),
        "first_quote_date": quote_dates[0].isoformat() if quote_dates else None,
        "last_quote_date": quote_dates[-1].isoformat() if quote_dates else None,
        "weekday_anchor": int(args.weekday),
        "planned_queries": planned_queries,
        "credit_cap": args.credit_cap,
    }, indent=2))
    if not args.execute:
        return 0

    api_key = os.environ.get("MARKETDATA_API_KEY", "").strip()
    if not api_key:
        env_path = repo_root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("MARKETDATA_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        raise SystemExit("MARKETDATA_API_KEY not found in environment or .env")

    credits = 0
    written = 0
    session = requests.Session()
    for ticker in tickers:
        no_data_streak = 0
        for qd in quote_dates:
            if credits >= args.credit_cap:
                print(f"[PHANTOM] credit cap reached: {credits}/{args.credit_cap}")
                print(json.dumps({"rows_written": written, "estimated_credits": credits, "db_path": str(db_path)}, indent=2))
                return 0
            qd_str = qd.isoformat()
            params = {
                "date": qd_str,
                "from": (qd + timedelta(days=7)).isoformat(),
                "to": (qd + timedelta(days=60)).isoformat(),
                "strikeLimit": args.strike_limit,
                "range": "all",
                "minOpenInterest": args.min_open_interest,
            }
            key = _query_key(ticker, qd_str, params)
            if db.audit_exists(key):
                continue
            started = utc_now()
            try:
                data = fetch_chain(session, api_key, ticker, qd_str, params)
                if data.get("s") != "ok":
                    db.write_backfill_audit(key, ticker, qd_str, params, "NO_DATA", 0, 1, data.get("errmsg", ""), started)
                    credits += 1
                    no_data_streak += 1
                    if no_data_streak <= 3:
                        print(f"[PHANTOM] {ticker} {qd_str}: no_data ({no_data_streak}/{args.max_no_data_streak})")
                    if no_data_streak >= args.max_no_data_streak:
                        print(f"[PHANTOM] {ticker}: stopped after {no_data_streak} consecutive no-data dates")
                        break
                    continue
                rows = normalize_marketdata_chain(data, ticker, qd_str)
                row_count = db.upsert_chain_rows(rows)
                est = _estimated_credits(row_count)
                db.write_backfill_audit(key, ticker, qd_str, params, "OK", row_count, est, "", started)
                credits += est
                written += row_count
                no_data_streak = 0
                print(f"[PHANTOM] {ticker} {qd_str}: rows={row_count} credits~{est} total_credits~{credits}")
                time.sleep(args.sleep)
            except Exception as exc:
                db.write_backfill_audit(key, ticker, qd_str, params, "ERROR", 0, 1, str(exc), started)
                credits += 1
    print(json.dumps({"rows_written": written, "estimated_credits": credits, "db_path": str(db_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
