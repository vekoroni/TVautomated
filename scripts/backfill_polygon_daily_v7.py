"""Persist adjusted Polygon daily OHLCV for the controlled actuarial v7 rebuild."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests


DEFAULT_OUTPUT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\daily_history_v7")
BASE_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_ticker(ticker: str, start: str, end: str, api_key: str) -> pd.DataFrame:
    response = None
    for attempt in range(2):
        response = requests.get(
            BASE_URL.format(ticker=quote(ticker, safe=""), start=start, end=end),
            params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key},
            timeout=(10, 20),
        )
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(2 ** attempt)
    assert response is not None
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"OK", "DELAYED"}:
        raise RuntimeError(f"Polygon returned status {payload.get('status')}: {payload.get('error', '')}")
    rows = payload.get("results", [])
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(rows).rename(
        columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    )
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    return frame[["date", "open", "high", "low", "close", "volume"]].sort_values("date")


def _persist_one(ticker: str, start: str, end: str, output: Path, api_key: str) -> tuple[str, dict]:
    target = output / f"{ticker}.csv"
    if target.exists():
        existing = pd.read_csv(target)
        if len(existing) >= 61 and str(existing["date"].max()) >= end:
            return ticker, {
                "status": "REUSED",
                "rows": len(existing),
                "min_date": str(existing["date"].min()),
                "max_date": str(existing["date"].max()),
                "sha256": _sha256(target),
                "extreme_adjusted_moves_over_60pct": int((existing["close"].pct_change().abs() > 0.60).sum()),
            }
    frame = fetch_ticker(ticker, start, end, api_key)
    if len(frame) < 61:
        return ticker, {"status": "INSUFFICIENT_DATA", "rows": len(frame)}
    temporary = target.with_suffix(".csv.tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, target)
    returns = frame["close"].pct_change().abs()
    return ticker, {
        "status": "PERSISTED",
        "rows": len(frame),
        "min_date": frame["date"].min(),
        "max_date": frame["date"].max(),
        "sha256": _sha256(target),
        "extreme_adjusted_moves_over_60pct": int((returns > 0.60).sum()),
    }


def _write_manifest(output: Path, start: str, end: str, records: dict[str, dict], status: str) -> dict:
    manifest = {
        "status": status,
        "provider": "Polygon",
        "endpoint": "/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
        "adjusted": True,
        "timespan": "day",
        "start": start,
        "end": end,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "tickers": dict(sorted(records.items())),
    }
    manifest_path = output / "_source_manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest


def backfill(tickers: list[str], start: str, end: str, output: Path, workers: int) -> dict:
    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is required in the environment")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "_source_manifest.json"
    records: dict[str, dict] = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("start") == start and previous.get("end") == end:
            records = previous.get("tickers", {})
    terminal = {"PERSISTED", "REUSED", "INSUFFICIENT_DATA"}
    pending = [ticker for ticker in tickers if records.get(ticker, {}).get("status") not in terminal]
    _write_manifest(output, start, end, records, "IN_PROGRESS")
    print(f"resume: {len(records)} recorded, {len(pending)} pending", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_persist_one, ticker, start, end, output, api_key): ticker
            for ticker in pending
        }
        for index, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            try:
                _, record = future.result()
            except Exception as exc:
                record = {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
            records[ticker] = record
            if index % 25 == 0 or index == len(pending) or record["status"] == "ERROR":
                print(f"[{index}/{len(pending)}] {ticker}: {record['status']} {record.get('rows', 0)} rows", flush=True)
            _write_manifest(output, start, end, records, "IN_PROGRESS")
    complete_count = sum(records.get(ticker, {}).get("status") in terminal for ticker in tickers)
    status = "COMPLETE" if complete_count == len(tickers) else "PARTIAL_ERROR"
    return _write_manifest(output, start, end, records, status)


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tickers", help="Comma-separated ticker symbols")
    source.add_argument("--universe", type=Path, help="CSV containing a ticker or symbol column")
    parser.add_argument("--start", default="2021-08-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.universe:
        universe = pd.read_csv(args.universe)
        column = next((name for name in universe.columns if name.lower() in {"ticker", "symbol"}), None)
        if column is None:
            raise ValueError("universe CSV requires a ticker or symbol column")
        tickers = universe[column].dropna().astype(str).str.upper().str.strip().drop_duplicates().tolist()
    else:
        tickers = [value.strip().upper() for value in args.tickers.split(",") if value.strip()]
    backfill(tickers, args.start, args.end, args.output, args.workers)


if __name__ == "__main__":
    main()
