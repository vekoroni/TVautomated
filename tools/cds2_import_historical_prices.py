"""Offline CDS-2 importer for package and data/daily OHLCV histories.

This module contains no provider client and performs no network requests.
Validated package history is loaded first; newer data/daily rows are then
upserted, with any differing overlaps preserved in the revision audit.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import HistoricalPriceDatabase, normalise_daily_ohlcv  # noqa: E402


def _package_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        payload.get("ohlcv_daily"),
        (payload.get("timeseries") or {}).get("ohlcv_daily"),
        payload.get("ohlcv"),
        payload.get("daily_df"),
    )
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return candidate
        if isinstance(candidate, dict):
            dates = candidate.get("date") or candidate.get("t")
            opens = candidate.get("open") or candidate.get("o")
            highs = candidate.get("high") or candidate.get("h")
            lows = candidate.get("low") or candidate.get("l")
            closes = candidate.get("close") or candidate.get("c")
            volumes = candidate.get("volume") or candidate.get("v")
            if all(isinstance(values, list) for values in (dates, opens, highs, lows, closes, volumes)):
                return [
                    {
                        "date": values[0], "open": values[1], "high": values[2],
                        "low": values[3], "close": values[4], "volume": values[5],
                    }
                    for values in zip(dates, opens, highs, lows, closes, volumes)
                ]
    return []


def _backup_existing(database_path: Path) -> Path | None:
    if not database_path.exists() or database_path.stat().st_size == 0:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"{database_path.stem}_pre_import_{stamp}.sqlite"
    shutil.copy2(database_path, destination)
    return destination


def run_import(
    *,
    database_path: Path,
    daily_dir: Path,
    packages_dir: Path,
    run_id: str,
    dry_run: bool = False,
    limit: int | None = None,
    progress_every: int = 100,
) -> dict[str, Any]:
    package_paths = sorted(packages_dir.glob("*.package.json"))
    daily_paths = sorted(daily_dir.glob("*.csv"))
    if limit is not None:
        package_paths = package_paths[:limit]
        daily_paths = daily_paths[:limit]
    database = HistoricalPriceDatabase(database_path)
    if not dry_run:
        database.initialise()

    report: dict[str, Any] = {
        "contract_version": "cds2_historical_price_import_v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_path.resolve()),
        "run_id": run_id,
        "dry_run": dry_run,
        "network_calls": 0,
        "package_files_found": len(package_paths),
        "daily_files_found": len(daily_paths),
        "package_files_imported": 0,
        "daily_files_imported": 0,
        "input_rows": 0,
        "valid_rows": 0,
        "inserted_rows": 0,
        "revised_rows": 0,
        "unchanged_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "errors": [],
        "source_gaps": [],
    }

    def account(result) -> None:
        report["input_rows"] += result.input_rows
        report["valid_rows"] += result.valid_rows
        report["inserted_rows"] += result.inserted_rows
        report["revised_rows"] += result.revised_rows
        report["unchanged_rows"] += result.unchanged_rows
        report["duplicate_rows"] += result.duplicate_rows
        report["rejected_rows"] += result.rejected_rows

    processed = 0
    for path in package_paths:
        ticker = path.name[: -len(".package.json")].upper()
        try:
            with path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            rows = _package_rows(payload)
            if not rows:
                report["source_gaps"].append(
                    {
                        "source": "PACKAGE",
                        "path": str(path),
                        "reason": "PACKAGE_HAS_NO_OHLCV",
                    }
                )
                continue
            source = str((payload.get("timeseries") or {}).get("source") or "POLYGON")
            partial_dates: tuple[str, ...] = ()
            if payload.get("intraday_partial") and rows:
                partial_dates = (str(rows[-1].get("date", ""))[:10],)
            if dry_run:
                frame, rejected = normalise_daily_ohlcv(rows)
                report["input_rows"] += len(rows)
                report["valid_rows"] += len(frame)
                report["duplicate_rows"] += int(frame.attrs.get("duplicate_rows", 0))
                report["rejected_rows"] += rejected
            else:
                result = database.ingest(
                    ticker,
                    rows,
                    provider=source,
                    source_kind="MIGRATION_PACKAGE",
                    source_run_id=run_id,
                    partial_dates=partial_dates,
                )
                account(result)
            report["package_files_imported"] += 1
        except Exception as error:
            if len(report["errors"]) < 200:
                report["errors"].append(
                    {"source": "PACKAGE", "path": str(path), "error": str(error)}
                )
        processed += 1
        if progress_every and processed % progress_every == 0:
            print(f"package progress: {processed}/{len(package_paths)}", flush=True)

    processed = 0
    for path in daily_paths:
        ticker = path.stem.upper()
        try:
            frame = pd.read_csv(path)
            if dry_run:
                normalised, rejected = normalise_daily_ohlcv(frame)
                report["input_rows"] += len(frame)
                report["valid_rows"] += len(normalised)
                report["duplicate_rows"] += int(
                    normalised.attrs.get("duplicate_rows", 0)
                )
                report["rejected_rows"] += rejected
            else:
                result = database.ingest(
                    ticker,
                    frame,
                    provider="POLYGON",
                    source_kind="MIGRATION_DAILY_CACHE",
                    source_run_id=run_id,
                )
                account(result)
            report["daily_files_imported"] += 1
        except Exception as error:
            if len(report["errors"]) < 200:
                report["errors"].append(
                    {"source": "DAILY_CACHE", "path": str(path), "error": str(error)}
                )
        processed += 1
        if progress_every and processed % progress_every == 0:
            print(f"daily progress: {processed}/{len(daily_paths)}", flush=True)

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["error_count"] = len(report["errors"])
    report["source_gap_count"] = len(report["source_gaps"])
    if not dry_run:
        report["database_health"] = database.health()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "canonical" / "historical_prices.sqlite",
    )
    parser.add_argument("--daily-dir", type=Path, default=ROOT / "data" / "daily")
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-backup", action="store_true")
    arguments = parser.parse_args()

    backup = None
    if not arguments.dry_run and not arguments.no_backup:
        backup = _backup_existing(arguments.database)
    report = run_import(
        database_path=arguments.database,
        daily_dir=arguments.daily_dir,
        packages_dir=arguments.packages_dir,
        run_id=arguments.run_id,
        dry_run=arguments.dry_run,
        limit=arguments.limit,
    )
    report["pre_import_backup"] = str(backup) if backup else None
    report_path = arguments.report or (
        ROOT
        / "data"
        / "canonical"
        / "reports"
        / f"cds2_import_{arguments.run_id}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "network_calls": report["network_calls"],
        "inserted_rows": report["inserted_rows"],
        "revised_rows": report["revised_rows"],
        "error_count": report["error_count"],
    }, sort_keys=True))
    return 0 if report["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
