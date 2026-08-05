"""Fail-closed validation gate for a staged actuarial v7 parquet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


REQUIRED = {
    "ticker", "date", "calculation_version", "schema_version",
    "bucket_schema_version", "actuarial_core_hash", "source_name",
    "source_dataset_fingerprint", "source_adjustment_policy", "build_id",
    "mature_5d", "mature_10d", "mature_20d", "label_asof_date",
    "outcome_5d_return", "outcome_10d_return", "outcome_20d_return",
    "momentum_score", "state_v2", "momentum_next", "momentum_delta",
    "atr_next", "atr_delta", "adx_next", "adx_delta",
    "transition_flag_v2", "future_momentum_bucket", "early_candidate",
}
LIVE_PATH = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(path: Path, *, allow_live: bool = False) -> dict:
    failures: list[str] = []
    if path.resolve() == LIVE_PATH.resolve() and not allow_live:
        failures.append(
            "validator target is the live v7 path; use --allow-live only for "
            "read-only post-cutover validation"
        )
    parquet = pq.ParquetFile(path)
    columns = set(parquet.schema_arrow.names)
    missing = sorted(REQUIRED.difference(columns))
    if missing:
        failures.append(f"missing required columns: {missing}")
    if not missing:
        scan_columns = [
            "ticker", "date", "calculation_version",
            "mature_5d", "mature_10d", "mature_20d",
            "outcome_5d_return", "outcome_10d_return", "outcome_20d_return",
        ]
        tickers: set[str] = set()
        versions: set[str] = set()
        last_date: dict[str, str] = {}
        duplicate_keys = 0
        canonical_failures = 0
        maturity_failures = {5: 0, 10: 0, 20: 0}
        scanned_rows = 0
        for batch in parquet.iter_batches(batch_size=100_000, columns=scan_columns):
            frame = batch.to_pandas()
            scanned_rows += len(frame)
            date_text = frame["date"].astype(str)
            canonical = pd.to_datetime(date_text, errors="coerce").dt.strftime("%Y-%m-%d")
            canonical_failures += int((canonical.isna() | canonical.ne(date_text)).sum())
            for ticker, date_value in zip(frame["ticker"].astype(str), date_text):
                previous = last_date.get(ticker)
                if previous is not None and date_value <= previous:
                    duplicate_keys += 1
                last_date[ticker] = date_value
                tickers.add(ticker)
            versions.update(frame["calculation_version"].dropna().astype(str).unique())
            for horizon in (5, 10, 20):
                mature = frame[f"mature_{horizon}d"].fillna(False).astype(bool)
                outcome = frame[f"outcome_{horizon}d_return"]
                maturity_failures[horizon] += int(outcome[mature].isna().sum())
                maturity_failures[horizon] += int(outcome[~mature].notna().sum())
        if canonical_failures:
            failures.append(f"non-canonical date rows: {canonical_failures}")
        if duplicate_keys:
            failures.append(f"duplicate/non-increasing ticker-date keys: {duplicate_keys}")
        for horizon, count in maturity_failures.items():
            if count:
                failures.append(f"{horizon}d maturity/outcome inconsistencies: {count}")
        if versions != {"actuarial_core_v7.0.0"}:
            failures.append(f"unexpected calculation versions: {sorted(versions)}")
        if scanned_rows != parquet.metadata.num_rows:
            failures.append(f"row scan mismatch: {scanned_rows} != {parquet.metadata.num_rows}")
        if any(str(column).lower().startswith("unnamed") for column in columns):
            failures.append("index-artifact column present")
    else:
        tickers = set()
    report = {
        "status": "PASS" if not failures else "FAIL",
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "rows": parquet.metadata.num_rows,
        "tickers": len(tickers),
        "failures": failures,
    }
    report_path = path.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Permit post-cutover validation of the canonical live v7 file",
    )
    args = parser.parse_args()
    report = validate(args.path, allow_live=args.allow_live)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
