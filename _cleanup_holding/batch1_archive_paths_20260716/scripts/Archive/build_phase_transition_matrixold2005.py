from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover - pandas can still read parquet in deployed envs
    pq = None


EMPTY_PHASES = {"", "NAN", "NONE", "NULL", "NA", "N/A"}


def _normalise_phase(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip().str.upper()
    return out.where(~out.isin(EMPTY_PHASES), "")


def _parquet_row_count(path: Path) -> int | None:
    if pq is None:
        return None
    try:
        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:
        return None


def _available_columns(path: Path) -> set[str]:
    if pq is not None:
        try:
            return set(pq.ParquetFile(path).schema_arrow.names)
        except Exception:
            pass
    return set(pd.read_parquet(path, engine="auto").columns)


def build_transition_matrix(
    actuarial_db: Path,
    output_dir: Path,
    phase_column: str = "phase_v2",
    fallback_columns: Iterable[str] = ("phase_v2", "wyckoff_phase_bucket", "crabel_state"),
) -> dict:
    if not actuarial_db.exists() or actuarial_db.stat().st_size <= 0:
        raise FileNotFoundError(f"Actuarial database not found or empty: {actuarial_db}")

    columns = _available_columns(actuarial_db)
    required = {"ticker", "date", phase_column}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Actuarial database missing required columns: {missing}")

    read_cols = ["ticker", "date"]
    for col in [phase_column, *fallback_columns]:
        if col in columns and col not in read_cols:
            read_cols.append(col)

    df = pd.read_parquet(actuarial_db, columns=read_cols)
    phase = _normalise_phase(df[phase_column])
    for fallback in fallback_columns:
        if fallback == phase_column or fallback not in df.columns:
            continue
        fb = _normalise_phase(df[fallback])
        phase = phase.where(phase.ne(""), fb)

    df = df.assign(phase_current=phase)
    df = df[df["phase_current"].ne("")].copy()
    df["ticker"] = df["ticker"].fillna("").astype(str).str.upper().str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["ticker"].ne("") & df["date"].notna()].sort_values(["ticker", "date"])
    df["phase_next"] = df.groupby("ticker", sort=False)["phase_current"].shift(-1)
    df = df[df["phase_next"].notna() & df["phase_next"].astype(str).str.strip().ne("")]

    counts = pd.crosstab(df["phase_current"], df["phase_next"]).sort_index(axis=0).sort_index(axis=1)
    probs = counts.div(counts.sum(axis=1), axis=0).fillna(0.0)
    long = counts.stack().rename("transition_count").reset_index()
    long["transition_probability"] = [
        float(probs.loc[row.phase_current, row.phase_next])
        for row in long.itertuples(index=False)
    ]
    long = long.sort_values(
        ["phase_current", "transition_probability", "transition_count"],
        ascending=[True, False, False],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    matrix_path = output_dir / f"actuarial_phase_transition_matrix_{stamp}.csv"
    counts_path = output_dir / f"actuarial_phase_transition_counts_{stamp}.csv"
    long_path = output_dir / f"actuarial_phase_transition_matrix_long_{stamp}.csv"
    meta_path = output_dir / f"actuarial_phase_transition_matrix_{stamp}.json"

    latest_matrix_path = output_dir / "actuarial_phase_transition_matrix_latest.csv"
    latest_counts_path = output_dir / "actuarial_phase_transition_counts_latest.csv"
    latest_long_path = output_dir / "actuarial_phase_transition_matrix_long_latest.csv"
    latest_meta_path = output_dir / "actuarial_phase_transition_matrix_latest.json"

    probs.to_csv(matrix_path, float_format="%.8f")
    counts.to_csv(counts_path)
    long.to_csv(long_path, index=False, float_format="%.8f")
    probs.to_csv(latest_matrix_path, float_format="%.8f")
    counts.to_csv(latest_counts_path)
    long.to_csv(latest_long_path, index=False, float_format="%.8f")

    meta = {
        "builder": "build_phase_transition_matrix.py",
        "built_at_local": datetime.now().isoformat(timespec="seconds"),
        "source_actuarial_database": str(actuarial_db),
        "source_size_bytes": actuarial_db.stat().st_size,
        "source_last_write": datetime.fromtimestamp(actuarial_db.stat().st_mtime).isoformat(timespec="seconds"),
        "phase_column": phase_column,
        "fallback_columns": list(fallback_columns),
        "input_rows": _parquet_row_count(actuarial_db),
        "usable_transition_rows": int(len(df)),
        "phase_states": [str(x) for x in probs.index.tolist()],
        "outputs": {
            "probability_matrix_csv": str(matrix_path),
            "probability_matrix_latest_csv": str(latest_matrix_path),
            "count_matrix_csv": str(counts_path),
            "count_matrix_latest_csv": str(latest_counts_path),
            "long_form_csv": str(long_path),
            "long_form_latest_csv": str(latest_long_path),
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    latest_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Build actuarial phase-to-phase transition matrix.")
    parser.add_argument("--actuarial-db", required=True, help="Path to actuarial_database_v6.parquet")
    parser.add_argument("--output-dir", required=True, help="Directory for transition matrix artifacts")
    parser.add_argument("--phase-column", default="phase_v2", help="Current phase column to use")
    parser.add_argument("--dry-run", action="store_true", help="Validate source/schema without writing outputs")
    args = parser.parse_args()

    actuarial_db = Path(args.actuarial_db)
    output_dir = Path(args.output_dir)
    if args.dry_run:
        columns = _available_columns(actuarial_db)
        required = {"ticker", "date", args.phase_column}
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"Actuarial database missing required columns: {missing}")
        print(json.dumps({
            "ok": True,
            "source_actuarial_database": str(actuarial_db),
            "source_size_bytes": actuarial_db.stat().st_size,
            "input_rows": _parquet_row_count(actuarial_db),
            "phase_column": args.phase_column,
        }, indent=2))
        return 0

    meta = build_transition_matrix(actuarial_db, output_dir, args.phase_column)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
