"""Build EV3 Stage EV-0 barrier sidecar and candidate diagnostics.

The command is offline, staged by default, and does not modify the live
actuarial database or connect EV3 to any production consumer.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vanguard.ev3_stage0 import (  # noqa: E402
    BarrierGrid,
    EV3_BARRIER_SCHEMA_VERSION,
    EV3_STAGE0_VERSION,
    STATE_DIMENSIONS,
    accumulate_ticker_barriers,
    barrier_cache_audit,
    finalise_barrier_cache,
    merge_barrier_accumulators,
    sha256_file,
    validate_ev3_dataframe,
)


DEFAULT_ACTUARIAL_DB = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")
DEFAULT_DAILY_DIR = ROOT / "data" / "daily_history_v7"
DEFAULT_OUTPUT = Path(r"C:\Users\ACKVerissimo\vanguard\data\staging\ev3_barrier_outcome_cache.parquet")
GOVERNED_FINAL_OUTPUT = Path(r"C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.parquet")


def _parse_float_grid(value: str) -> tuple[float, ...]:
    result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not result:
        raise argparse.ArgumentTypeError("grid cannot be empty")
    return result


def _parse_int_grid(value: str) -> tuple[int, ...]:
    result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not result:
        raise argparse.ArgumentTypeError("horizons cannot be empty")
    return result


def _read_source_manifest(daily_dir: Path) -> tuple[dict[str, Any], str | None]:
    path = daily_dir / "_source_manifest.json"
    if not path.exists():
        return {}, None
    return json.loads(path.read_text(encoding="utf-8")), sha256_file(path)


def _ticker_row_groups(parquet_file: pq.ParquetFile) -> list[tuple[int, str]]:
    ticker_index = parquet_file.schema_arrow.names.index("ticker")
    result: list[tuple[int, str]] = []
    for row_group_index in range(parquet_file.num_row_groups):
        metadata = parquet_file.metadata.row_group(row_group_index).column(ticker_index).statistics
        if metadata is None or metadata.min != metadata.max:
            table = parquet_file.read_row_group(row_group_index, columns=["ticker"]).to_pandas()
            tickers = table["ticker"].dropna().astype(str).str.upper().unique()
            if len(tickers) != 1:
                raise ValueError(f"row group {row_group_index} contains multiple tickers")
            ticker = str(tickers[0])
        else:
            ticker = str(metadata.min).upper()
        result.append((row_group_index, ticker))
    return result


def _chunks(values: list[tuple[int, str]], size: int) -> list[list[tuple[int, str]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _process_barrier_chunk(
    payload: tuple[Path, Path, list[tuple[int, str]], BarrierGrid],
) -> tuple[dict, dict[str, dict[str, Any]]]:
    actuarial_db, daily_dir, row_groups, grid = payload
    parquet_file = pq.ParquetFile(actuarial_db)
    columns = ["ticker", "date", *STATE_DIMENSIONS]
    local_accumulators = {}
    coverage: dict[str, dict[str, Any]] = {}
    for row_group_index, ticker in row_groups:
        history_path = daily_dir / f"{ticker}.csv"
        if not history_path.exists():
            coverage[ticker] = {"status": "MISSING_HISTORY", "used_rows": 0}
            continue
        state_rows = parquet_file.read_row_group(row_group_index, columns=columns).to_pandas()
        history = pd.read_csv(history_path, usecols=["date", "high", "low", "close"])
        stats = accumulate_ticker_barriers(state_rows, history, local_accumulators, grid)
        stats["status"] = "USED"
        stats["history_sha256"] = sha256_file(history_path)
        coverage[ticker] = stats
    return local_accumulators, coverage


def build_barrier_sidecar(args: argparse.Namespace) -> dict[str, Any]:
    actuarial_db = args.actuarial_db.resolve()
    daily_dir = args.daily_dir.resolve()
    output = args.output.resolve()
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    if args.chunk_size < 1:
        raise ValueError("chunk-size must be at least 1")
    if output == GOVERNED_FINAL_OUTPUT.resolve() and not args.allow_final_output:
        raise ValueError("refusing governed final output without --allow-final-output")
    if output == actuarial_db:
        raise ValueError("barrier output cannot overwrite the actuarial database")
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"output already exists: {output}; use --overwrite after review")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"stale temporary output requires review: {temporary}")

    grid = BarrierGrid(args.target_grid, args.stop_grid, args.horizons, args.shrinkage_k)
    parquet_file = pq.ParquetFile(actuarial_db)
    required = {"ticker", "date", *STATE_DIMENSIONS}
    missing = required.difference(parquet_file.schema_arrow.names)
    if missing:
        raise ValueError(f"actuarial database missing columns: {', '.join(sorted(missing))}")

    requested = {ticker.upper() for ticker in args.tickers} if args.tickers else None
    row_groups = [item for item in _ticker_row_groups(parquet_file) if requested is None or item[1] in requested]
    if args.max_tickers:
        row_groups = row_groups[: args.max_tickers]
    if not row_groups:
        raise ValueError("no matching tickers selected")

    accumulators = {}
    coverage: dict[str, dict[str, Any]] = {}
    work_chunks = _chunks(row_groups, args.chunk_size)
    payloads = [(actuarial_db, daily_dir, chunk, grid) for chunk in work_chunks]
    if args.workers == 1:
        results = map(_process_barrier_chunk, payloads)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=args.workers)
        results = executor.map(_process_barrier_chunk, payloads)
    processed = 0
    try:
        for local_accumulators, local_coverage in results:
            merge_barrier_accumulators(accumulators, local_accumulators)
            coverage.update(local_coverage)
            processed += len(local_coverage)
            if args.verbose:
                print(f"[{processed}/{len(row_groups)}] ticker histories processed")
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    built_at = datetime.now(timezone.utc).isoformat()
    cache = finalise_barrier_cache(accumulators, grid, built_at_utc=built_at)
    if cache.empty:
        raise ValueError("barrier build produced no rows")
    cache.to_parquet(temporary, index=False, compression="snappy")
    temporary.replace(output)

    source_manifest, source_manifest_sha256 = _read_source_manifest(daily_dir)
    audit = barrier_cache_audit(cache)
    audit.update(
        status="PASS" if audit["status"] == "PASS" else "FAIL",
        stage="EV-0",
        non_authoritative=True,
        production_consumer_enabled=False,
        built_at_utc=built_at,
        output=str(output),
        output_sha256=sha256_file(output),
        actuarial_database=str(actuarial_db),
        actuarial_database_size=actuarial_db.stat().st_size,
        actuarial_database_mtime_ns=actuarial_db.stat().st_mtime_ns,
        daily_directory=str(daily_dir),
        source_manifest_sha256=source_manifest_sha256,
        source_provider=source_manifest.get("provider"),
        source_adjusted=source_manifest.get("adjusted"),
        selected_tickers=len(row_groups),
        used_tickers=sum(1 for value in coverage.values() if value["status"] == "USED"),
        missing_history_tickers=sum(1 for value in coverage.values() if value["status"] == "MISSING_HISTORY"),
        target_grid=list(grid.targets),
        stop_grid=list(grid.stops),
        horizons=list(grid.horizons),
        shrinkage_k=grid.shrinkage_k,
        stage0_version=EV3_STAGE0_VERSION,
        barrier_schema_version=EV3_BARRIER_SCHEMA_VERSION,
        workers=args.workers,
        chunk_size=args.chunk_size,
        ticker_coverage=coverage,
    )
    audit_path = output.with_suffix(".audit.json")
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return audit


def build_input_diagnostics(args: argparse.Namespace) -> dict[str, Any]:
    source = args.candidates.resolve()
    if source.suffix.lower() == ".parquet":
        frame = pd.read_parquet(source)
    else:
        frame = pd.read_csv(source, low_memory=False)
    accepted, diagnostics = validate_ev3_dataframe(
        frame,
        phase=args.phase,
        require_contract=not args.thesis_only,
        max_quote_age_seconds=args.max_quote_age_seconds,
        minimum_open_interest=args.minimum_open_interest,
    )
    prefix = args.diagnostics_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    accepted_path = prefix.with_name(prefix.name + "_accepted.parquet")
    rejection_path = prefix.with_name(prefix.name + "_diagnostics.csv")
    accepted.to_parquet(accepted_path, index=False)
    diagnostics.to_csv(rejection_path, index=False)
    summary = {
        "stage": "EV-0",
        "non_authoritative": True,
        "source": str(source),
        "rows": len(frame),
        "accepted": len(accepted),
        "rejected": int((diagnostics["ev3_status"] == "REJECTED").sum()),
        "reason_counts": diagnostics["ev3_reason_code"].value_counts(dropna=False).to_dict(),
        "accepted_output": str(accepted_path),
        "diagnostics_output": str(rejection_path),
    }
    prefix.with_name(prefix.name + "_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    barriers = subparsers.add_parser("barriers", help="build the offline barrier sidecar")
    barriers.add_argument("--actuarial-db", type=Path, default=DEFAULT_ACTUARIAL_DB)
    barriers.add_argument("--daily-dir", type=Path, default=DEFAULT_DAILY_DIR)
    barriers.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    barriers.add_argument("--target-grid", type=_parse_float_grid, default=BarrierGrid().targets)
    barriers.add_argument("--stop-grid", type=_parse_float_grid, default=BarrierGrid().stops)
    barriers.add_argument("--horizons", type=_parse_int_grid, default=BarrierGrid().horizons)
    barriers.add_argument("--shrinkage-k", type=float, default=30.0)
    barriers.add_argument("--tickers", nargs="*", default=[])
    barriers.add_argument("--max-tickers", type=int)
    barriers.add_argument("--workers", type=int, default=1)
    barriers.add_argument("--chunk-size", type=int, default=25)
    barriers.add_argument("--overwrite", action="store_true")
    barriers.add_argument("--allow-final-output", action="store_true")
    barriers.add_argument("--verbose", action="store_true")

    diagnostics = subparsers.add_parser("diagnostics", help="validate a current candidate artefact")
    diagnostics.add_argument("--candidates", type=Path, required=True)
    diagnostics.add_argument("--diagnostics-prefix", type=Path, required=True)
    diagnostics.add_argument("--phase", choices=["EOD", "MORNING_REFRESH"], default="EOD")
    diagnostics.add_argument("--thesis-only", action="store_true")
    diagnostics.add_argument("--max-quote-age-seconds", type=int)
    diagnostics.add_argument("--minimum-open-interest", type=int, default=0)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "barriers":
        summary = build_barrier_sidecar(args)
    else:
        summary = build_input_diagnostics(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
