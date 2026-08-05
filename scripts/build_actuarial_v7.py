"""Build a reproducible actuarial v7 parquet from persisted daily CSV files.

This command never fetches an API and refuses to write to the live v6 path.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from vanguard.core.actuarial_core_v7 import build_ticker_observations


LIVE_PATH = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")
DEFAULT_DAILY = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\daily")
DEFAULT_OUTPUT = Path(r"C:\Users\ACKVerissimo\vanguard\data\staging\actuarial_database_v7_pilot.parquet")


def _source_fingerprint(paths: list[Path], source_manifest: dict) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        record = source_manifest.get("tickers", {}).get(path.stem.upper(), {})
        if record.get("sha256"):
            digest.update(record["sha256"].encode())
        else:
            digest.update(str(path.stat().st_size).encode())
            digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def _build_one(path: Path) -> tuple[str, dict, pd.DataFrame]:
    raw = pd.read_csv(path)
    ticker = path.stem.upper()
    coverage = {
        "rows": len(raw),
        "min_date": str(raw["date"].min()),
        "max_date": str(raw["date"].max()),
    }
    return ticker, coverage, build_ticker_observations(ticker, raw)


def build(daily_dir: Path, tickers: list[str], output: Path, workers: int = 1) -> dict:
    resolved_output = output.resolve()
    if resolved_output == LIVE_PATH.resolve():
        raise ValueError("staged builder refuses to overwrite the live v6 database")
    paths = [daily_dir / f"{ticker}.csv" for ticker in tickers]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing persisted daily files: {missing[:10]}")
    source_manifest_path = daily_dir / "_source_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8")) if source_manifest_path.exists() else {}
    adjustment_policy = "polygon_adjusted_true" if source_manifest.get("adjusted") is True else "upstream_adjusted_unverified"
    build_id = datetime.now(timezone.utc).strftime("v7-%Y%m%dT%H%M%SZ")
    fingerprint = _source_fingerprint(paths, source_manifest)
    source_coverage: dict[str, dict] = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"stale staged build requires review before retry: {temporary}")
    built_at = datetime.now(timezone.utc).isoformat()
    writer: pq.ParquetWriter | None = None
    rows = 0
    written_tickers = 0
    min_date: str | None = None
    max_date: str | None = None
    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for index, (ticker, coverage, observations) in enumerate(
                executor.map(_build_one, paths), 1
            ):
                source_coverage[ticker] = coverage
                if observations.empty:
                    continue
                observations["source_name"] = "persisted_daily_ohlcv"
                observations["source_dataset_fingerprint"] = fingerprint
                observations["source_adjustment_policy"] = adjustment_policy
                observations["build_id"] = build_id
                observations["built_at_utc"] = built_at
                if observations.duplicated(["ticker", "date", "calculation_version"]).any():
                    raise ValueError(f"duplicate v7 primary keys for {ticker}")
                table = pa.Table.from_pandas(observations, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(temporary, table.schema, compression="snappy")
                elif table.schema != writer.schema:
                    table = table.cast(writer.schema, safe=False)
                writer.write_table(table)
                rows += len(observations)
                written_tickers += 1
                ticker_min, ticker_max = observations["date"].min(), observations["date"].max()
                min_date = ticker_min if min_date is None else min(min_date, ticker_min)
                max_date = ticker_max if max_date is None else max(max_date, ticker_max)
                if index % 25 == 0 or index == len(paths):
                    print(f"[{index}/{len(paths)}] rows={rows:,} ticker={ticker}", flush=True)
    finally:
        if writer is not None:
            writer.close()
    if writer is None or rows == 0:
        raise ValueError("no eligible observations; each ticker needs at least 61 daily bars")
    os.replace(temporary, output)
    manifest = {
        "status": "BUILT_NOT_PROMOTED",
        "build_id": build_id,
        "output": str(output.resolve()),
        "rows": rows,
        "tickers": written_tickers,
        "min_date": min_date,
        "max_date": max_date,
        "source_dataset_fingerprint": fingerprint,
        "source_adjustment_policy": adjustment_policy,
        "source_manifest": str(source_manifest_path.resolve()) if source_manifest_path.exists() else None,
        "source_coverage": source_coverage,
    }
    manifest_path = output.with_suffix(".build.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-dir", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--tickers", default=None)
    selection.add_argument("--source-manifest", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.source_manifest:
        source = json.loads(args.source_manifest.read_text(encoding="utf-8"))
        if source.get("status") != "COMPLETE":
            raise ValueError("source manifest must be COMPLETE")
        tickers = sorted(
            ticker for ticker, record in source["tickers"].items()
            if record.get("status") in {"PERSISTED", "REUSED"}
        )
    else:
        values = args.tickers or "AAPL,MSFT,NVDA,SPY,QQQ"
        tickers = [value.strip().upper() for value in values.split(",") if value.strip()]
    print(json.dumps(build(args.daily_dir, tickers, args.output, args.workers), indent=2))


if __name__ == "__main__":
    main()
