"""Validate and reconcile the CDS-2 historical-price database offline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import HistoricalPriceDatabase, normalise_daily_ohlcv  # noqa: E402


def validate(
    database_path: Path,
    daily_dir: Path,
    *,
    import_report_path: Path | None = None,
    reconcile_batch_metadata: bool = True,
) -> dict[str, object]:
    database = HistoricalPriceDatabase(database_path)
    database.initialise()
    daily_files = sorted(daily_dir.glob("*.csv"))
    duplicate_rows = 0
    invalid_rows = 0
    parity_rows = 0
    parity_mismatches = 0
    latest_source_date: str | None = None

    connection = sqlite3.connect(database_path, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA temp_store = MEMORY")
    try:
        for path in daily_files:
            ticker = path.stem.upper()
            source = pd.read_csv(path)
            normalised, invalid = normalise_daily_ohlcv(source)
            duplicates = int(normalised.attrs.get("duplicate_rows", 0))
            duplicate_rows += duplicates
            invalid_rows += invalid
            if not normalised.empty:
                source_last = pd.Timestamp(normalised["date"].max()).date().isoformat()
                latest_source_date = max(latest_source_date or source_last, source_last)
            if reconcile_batch_metadata:
                connection.execute(
                    """
                    UPDATE ohlcv_ingest_batches
                    SET duplicate_rows = ?, rejected_rows = ?
                    WHERE batch_id = (
                        SELECT batch_id FROM ohlcv_ingest_batches
                        WHERE ticker = ? AND source_kind = 'MIGRATION_DAILY_CACHE'
                        ORDER BY completed_at DESC LIMIT 1
                    )
                    """,
                    (duplicates, invalid, ticker),
                )
            rows = connection.execute(
                """
                SELECT trading_date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE ticker = ? AND adjustment_convention = 'POLYGON_SPLIT_ADJUSTED'
                """,
                (ticker,),
            ).fetchall()
            canonical = {row["trading_date"]: row for row in rows}
            for row in normalised.itertuples(index=False):
                trading_date = pd.Timestamp(row.date).date().isoformat()
                stored = canonical.get(trading_date)
                parity_rows += 1
                if stored is None:
                    parity_mismatches += 1
                    continue
                for column in ("open", "high", "low", "close", "volume"):
                    current = float(stored[column])
                    expected = float(getattr(row, column))
                    if abs(current - expected) > max(1e-8, abs(expected) * 1e-9):
                        parity_mismatches += 1
                        break
        connection.commit()

        duplicate_keys = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT ticker, trading_date, adjustment_convention
                    FROM ohlcv_daily
                    GROUP BY ticker, trading_date, adjustment_convention
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )
        batch_totals = tuple(
            connection.execute(
                """
                SELECT
                    COALESCE(SUM(input_rows), 0), COALESCE(SUM(valid_rows), 0),
                    COALESCE(SUM(inserted_rows), 0), COALESCE(SUM(revised_rows), 0),
                    COALESCE(SUM(unchanged_rows), 0), COALESCE(SUM(duplicate_rows), 0),
                    COALESCE(SUM(rejected_rows), 0)
                FROM ohlcv_ingest_batches
                """
            ).fetchone()
        )
    finally:
        connection.close()

    source_gaps: list[dict[str, object]] = []
    importer_errors: list[dict[str, object]] = []
    if import_report_path and import_report_path.exists():
        prior = json.loads(import_report_path.read_text(encoding="utf-8"))
        for item in prior.get("errors", []):
            if item.get("error") == "package has no OHLCV rows":
                source_gaps.append(
                    {
                        "source": item.get("source"),
                        "path": item.get("path"),
                        "reason": "PACKAGE_HAS_NO_OHLCV",
                    }
                )
            else:
                importer_errors.append(item)

    health = database.health()
    labels = (
        "input_rows",
        "valid_rows",
        "inserted_rows",
        "revised_rows",
        "unchanged_rows",
        "duplicate_rows",
        "invalid_rows",
    )
    report = {
        "contract_version": "cds2_historical_price_validation_v1",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database_path.resolve()),
        "network_calls": 0,
        "database_health": health,
        "duplicate_primary_key_count": duplicate_keys,
        "source_daily_files": len(daily_files),
        "source_latest_date": latest_source_date,
        "daily_parity_rows": parity_rows,
        "daily_parity_mismatches": parity_mismatches,
        "normalised_duplicate_rows": duplicate_rows,
        "normalised_invalid_rows": invalid_rows,
        "batch_totals": dict(zip(labels, batch_totals)),
        "source_gap_count": len(source_gaps),
        "source_gaps": source_gaps,
        "importer_error_count": len(importer_errors),
        "importer_errors": importer_errors,
    }
    report["accepted"] = bool(
        health["integrity_check"] == "ok"
        and health["schema"]["valid"]
        and duplicate_keys == 0
        and parity_mismatches == 0
        and not importer_errors
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "canonical" / "historical_prices.sqlite",
    )
    parser.add_argument("--daily-dir", type=Path, default=ROOT / "data" / "daily")
    parser.add_argument("--import-report", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--no-reconcile", action="store_true")
    arguments = parser.parse_args()
    report = validate(
        arguments.database,
        arguments.daily_dir,
        import_report_path=arguments.import_report,
        reconcile_batch_metadata=not arguments.no_reconcile,
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "accepted": report["accepted"],
        "rows": report["database_health"]["rows"],
        "tickers": report["database_health"]["tickers"],
        "duplicate_primary_key_count": report["duplicate_primary_key_count"],
        "daily_parity_mismatches": report["daily_parity_mismatches"],
        "source_gap_count": report["source_gap_count"],
        "importer_error_count": report["importer_error_count"],
    }, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
