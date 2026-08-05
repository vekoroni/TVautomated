"""Resumable sharded actuarial v7 build followed by atomic consolidation."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from build_actuarial_v7 import LIVE_PATH, _source_fingerprint
from vanguard.core.actuarial_core_v7 import build_ticker_observations


TERMINAL_SOURCE = {"PERSISTED", "REUSED"}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _build_part(args: tuple[int, str, Path, Path, str, str, str, str]) -> dict[str, Any]:
    index, ticker, daily_path, part_path, build_id, fingerprint, adjustment, built_at = args
    raw = pd.read_csv(daily_path)
    observations = build_ticker_observations(ticker, raw)
    if observations.empty:
        raise ValueError(f"no eligible observations for {ticker}")
    observations["source_name"] = "persisted_daily_ohlcv"
    observations["source_dataset_fingerprint"] = fingerprint
    observations["source_adjustment_policy"] = adjustment
    observations["build_id"] = build_id
    observations["built_at_utc"] = built_at
    temporary = part_path.with_suffix(".parquet.tmp")
    observations.to_parquet(temporary, index=False, compression="snappy")
    os.replace(temporary, part_path)
    return {
        "index": index,
        "ticker": ticker,
        "status": "BUILT",
        "rows": len(observations),
        "min_date": observations["date"].min(),
        "max_date": observations["date"].max(),
        "part": str(part_path.resolve()),
    }


def _valid_part(path: Path) -> int:
    try:
        return pq.ParquetFile(path).metadata.num_rows
    except Exception:
        return 0


def build_shards(
    daily_dir: Path, source_manifest_path: Path, parts_dir: Path, workers: int, limit: int | None = None
) -> tuple[dict[str, Any], list[str]]:
    source = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source.get("status") != "COMPLETE":
        raise ValueError("source manifest must be COMPLETE")
    tickers = sorted(ticker for ticker, record in source["tickers"].items() if record["status"] in TERMINAL_SOURCE)
    if limit is not None:
        tickers = tickers[:limit]
    paths = [daily_dir / f"{ticker}.csv" for ticker in tickers]
    fingerprint = _source_fingerprint(paths, source)
    adjustment = "polygon_adjusted_true" if source.get("adjusted") is True else "upstream_adjusted_unverified"
    parts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = parts_dir / "_parts_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_dataset_fingerprint") != fingerprint:
            raise ValueError("parts directory belongs to a different source fingerprint")
    else:
        manifest = {
            "status": "IN_PROGRESS",
            "build_id": datetime.now(timezone.utc).strftime("v7-%Y%m%dT%H%M%SZ"),
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_dataset_fingerprint": fingerprint,
            "source_adjustment_policy": adjustment,
            "source_manifest": str(source_manifest_path.resolve()),
            "expected_tickers": len(tickers),
            "parts": {},
        }
    pending: list[tuple[int, str, Path, Path, str, str, str, str]] = []
    for index, (ticker, daily_path) in enumerate(zip(tickers, paths)):
        part_path = parts_dir / f"{index:05d}.parquet"
        existing = manifest["parts"].get(ticker)
        if existing and existing.get("index") == index and _valid_part(part_path) > 0:
            continue
        pending.append((index, ticker, daily_path, part_path, manifest["build_id"], fingerprint, adjustment, manifest["built_at_utc"]))
    print(f"resume: {len(manifest['parts']):,} recorded, {len(pending):,} pending", flush=True)
    _atomic_json(manifest_path, manifest)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_build_part, item): item[1] for item in pending}
        for completed, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            record = future.result()
            manifest["parts"][ticker] = record
            if completed % 25 == 0 or completed == len(pending):
                _atomic_json(manifest_path, manifest)
                print(f"[{completed}/{len(pending)}] total_parts={len(manifest['parts']):,} ticker={ticker}", flush=True)
    manifest["status"] = "COMPLETE" if len(manifest["parts"]) == len(tickers) else "IN_PROGRESS"
    _atomic_json(manifest_path, manifest)
    return manifest, tickers


def consolidate(manifest: dict[str, Any], tickers: list[str], output: Path) -> dict[str, Any]:
    if output.resolve() == LIVE_PATH.resolve():
        raise ValueError("sharded builder refuses to overwrite live v6")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".assembling.{manifest['build_id']}")
    if temporary.exists():
        raise FileExistsError(f"stale consolidation artifact requires review: {temporary}")
    records = [manifest["parts"][ticker] for ticker in tickers]
    records.sort(key=lambda record: record["index"])
    writer: pq.ParquetWriter | None = None
    rows = 0
    try:
        for index, record in enumerate(records, 1):
            table = pq.read_table(record["part"])
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="snappy")
            elif table.schema != writer.schema:
                table = table.cast(writer.schema, safe=False)
            writer.write_table(table)
            rows += table.num_rows
            if index % 250 == 0 or index == len(records):
                print(f"consolidate [{index}/{len(records)}] rows={rows:,}", flush=True)
    finally:
        if writer is not None:
            writer.close()
    os.replace(temporary, output)
    result = {
        "status": "BUILT_NOT_PROMOTED",
        "build_id": manifest["build_id"],
        "output": str(output.resolve()),
        "rows": rows,
        "tickers": len(records),
        "min_date": min(record["min_date"] for record in records),
        "max_date": max(record["max_date"] for record in records),
        "source_dataset_fingerprint": manifest["source_dataset_fingerprint"],
        "source_adjustment_policy": manifest["source_adjustment_policy"],
        "source_manifest": manifest["source_manifest"],
        "parts_manifest": str((Path(records[0]["part"]).parent / "_parts_manifest.json").resolve()),
    }
    _atomic_json(output.with_suffix(".build.json"), result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    manifest, tickers = build_shards(args.daily_dir, args.source_manifest, args.parts_dir, args.workers, args.limit)
    if manifest["status"] != "COMPLETE":
        raise RuntimeError("parts manifest is incomplete")
    print(json.dumps(consolidate(manifest, tickers, args.output), indent=2))


if __name__ == "__main__":
    main()
