from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover
    pq = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMPTY_PHASES = {"", "NAN", "NONE", "NULL", "NA", "N/A"}

# Phases considered "favourable forward" for a long directional buyer.
# MARKUP / COMPRESSION_BREAKOUT = thesis advancing; everything else = risk.
FAVOURABLE_NEXT_PHASES = {
    # Phase states retained by the governed actuarial contract:
    # CONTINUATION, EARLY_TRANSITION, EXHAUSTION
    # Favourable = thesis still advancing or consolidating.
    # Unfavourable = thesis ending or reversing.
    "CONTINUATION",       # Phase advancing — directional thesis intact
    "EARLY_TRANSITION",   # Transition beginning — neutral, monitor closely
    # EXHAUSTION is explicitly NOT favourable — thesis ending
}

# Minimum observations per (phase, regime, tier) cell before we trust the
# probability.  Cells below this threshold are flagged as SPARSE in outputs.
MIN_CELL_COUNT = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_phase(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip().str.upper()
    return out.where(~out.isin(EMPTY_PHASES), "")


def _normalise_label(series: pd.Series, fill: str = "UNKNOWN") -> pd.Series:
    out = series.fillna("").astype(str).str.strip().str.upper()
    return out.where(out.ne(""), fill)


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


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_transition_matrix(
    actuarial_db: Path,
    output_dir: Path,
    phase_column: str = "phase_v2",
    regime_column: str = "macro_regime",
    tier_column: str = "future_momentum_bucket",
    fallback_columns: Iterable[str] = ("phase_v2", "wyckoff_phase_bucket", "crabel_state"),
) -> dict:
    """
    Build Markov phase-transition matrices stratified by regime and tier.

    Outputs
    -------
    For each stratification level (global / per-regime / per-tier / per-regime+tier):
      - probability matrix CSV  (phase_current × phase_next)
      - count matrix CSV
      - long-form CSV with transition_risk_factor per row
    Plus a single metadata JSON covering the full run.
    """

    # ── 1. Validate source ──────────────────────────────────────────────────
    if not actuarial_db.exists() or actuarial_db.stat().st_size <= 0:
        raise FileNotFoundError(f"Actuarial database not found or empty: {actuarial_db}")

    columns = _available_columns(actuarial_db)
    required = {"ticker", "date", phase_column}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Actuarial database missing required columns: {missing}")

    # Warn but don't fail if stratification columns are absent
    regime_available = regime_column in columns
    tier_available = tier_column in columns
    if not regime_available:
        print(f"[WARN] regime_column '{regime_column}' not found — global matrix only")
    if not tier_available:
        print(f"[WARN] tier_column '{tier_column}' not found — tier stratification skipped")

    # ── 2. Load minimal column set ──────────────────────────────────────────
    read_cols = ["ticker", "date"]
    for col in [phase_column, *list(fallback_columns)]:
        if col in columns and col not in read_cols:
            read_cols.append(col)
    if regime_available:
        read_cols.append(regime_column)
    if tier_available:
        read_cols.append(tier_column)

    df = pd.read_parquet(actuarial_db, columns=read_cols)

    # ── 3. Resolve phase with fallback chain ────────────────────────────────
    phase = _normalise_phase(df[phase_column])
    for fallback in fallback_columns:
        if fallback == phase_column or fallback not in df.columns:
            continue
        fb = _normalise_phase(df[fallback])
        phase = phase.where(phase.ne(""), fb)

    df = df.assign(phase_current=phase)
    df = df[df["phase_current"].ne("")].copy()

    # ── 4. Clean dimensions ─────────────────────────────────────────────────
    df["ticker"] = df["ticker"].fillna("").astype(str).str.upper().str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["ticker"].ne("") & df["date"].notna()].sort_values(["ticker", "date"])

    if regime_available:
        df["regime"] = _normalise_label(df[regime_column], fill="UNKNOWN")
    else:
        df["regime"] = "ALL"

    if tier_available:
        df["tier"] = _normalise_label(df[tier_column], fill="UNKNOWN")
    else:
        df["tier"] = "ALL"

    # ── 5. Derive phase_next per ticker ─────────────────────────────────────
    df["phase_next"] = df.groupby("ticker", sort=False)["phase_current"].shift(-1)
    df = df[df["phase_next"].notna() & df["phase_next"].astype(str).str.strip().ne("")]
    usable_rows = int(len(df))

    # ── 6. Build matrices at each stratification level ──────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_long_frames: list[pd.DataFrame] = []
    sparse_warnings: list[dict] = []

    def _build_one(
        subset: pd.DataFrame,
        label: str,
        regime: str,
        tier: str,
    ) -> pd.DataFrame:
        """Build counts + probs for one subset; return long-form rows."""
        if subset.empty:
            return pd.DataFrame()

        counts = (
            pd.crosstab(subset["phase_current"], subset["phase_next"])
            .sort_index(axis=0)
            .sort_index(axis=1)
        )
        probs = counts.div(counts.sum(axis=1), axis=0).fillna(0.0)

        # Write stamped + latest CSVs for this slice
        safe_label = label.replace(" ", "_").replace("/", "-")
        for suffix, data in [("probability", probs), ("counts", counts)]:
            data.to_csv(
                output_dir / f"transition_{suffix}_{safe_label}_{stamp}.csv",
                float_format="%.8f",
            )
            data.to_csv(
                output_dir / f"transition_{suffix}_{safe_label}_latest.csv",
                float_format="%.8f",
            )

        # Build long form with transition_risk_factor
        long = counts.stack().rename("transition_count").reset_index()
        long["transition_probability"] = [
            float(probs.loc[r.phase_current, r.phase_next])
            for r in long.itertuples(index=False)
        ]
        long["regime"] = regime
        long["tier"] = tier
        long["stratification"] = label

        # transition_risk_factor: probability mass flowing into NON-favourable states
        # trf = 1 - P(phase_next in FAVOURABLE_NEXT_PHASES | phase_current)
        # Computed per phase_current row, then joined back
        fav_prob = (
            long[long["phase_next"].isin(FAVOURABLE_NEXT_PHASES)]
            .groupby("phase_current")["transition_probability"]
            .sum()
            .rename("fav_prob")
        )
        long = long.join(fav_prob, on="phase_current")
        long["transition_risk_factor"] = (1.0 - long["fav_prob"].fillna(0.0)).clip(0.0, 1.0)
        long.drop(columns=["fav_prob"], inplace=True)

        # Sparse flag
        row_counts = counts.sum(axis=1).rename("row_total")
        long = long.join(row_counts, on="phase_current")
        long["sparse"] = long["row_total"] < MIN_CELL_COUNT
        long.drop(columns=["row_total"], inplace=True)

        # Collect sparse warnings
        sparse_cells = long[long["sparse"]][["phase_current", "regime", "tier", "transition_count"]].drop_duplicates("phase_current")
        for _, sc in sparse_cells.iterrows():
            sparse_warnings.append({
                "stratification": label,
                "phase_current": sc["phase_current"],
                "regime": sc["regime"],
                "tier": sc["tier"],
                "total_observations": int(sc["transition_count"]),
                "minimum_required": MIN_CELL_COUNT,
            })

        long = long.sort_values(
            ["phase_current", "transition_probability", "transition_count"],
            ascending=[True, False, False],
        )
        return long

    # ── 6a. Global (no stratification) ──────────────────────────────────────
    frame = _build_one(df, label="global", regime="ALL", tier="ALL")
    if not frame.empty:
        all_long_frames.append(frame)

    # ── 6b. Per regime ───────────────────────────────────────────────────────
    if regime_available:
        for regime_val, grp in df.groupby("regime", sort=True):
            lbl = f"regime_{regime_val}"
            frame = _build_one(grp, label=lbl, regime=str(regime_val), tier="ALL")
            if not frame.empty:
                all_long_frames.append(frame)

    # ── 6c. Per tier ─────────────────────────────────────────────────────────
    if tier_available:
        for tier_val, grp in df.groupby("tier", sort=True):
            lbl = f"tier_{tier_val}"
            frame = _build_one(grp, label=lbl, regime="ALL", tier=str(tier_val))
            if not frame.empty:
                all_long_frames.append(frame)

    # ── 6d. Per regime × tier ────────────────────────────────────────────────
    if regime_available and tier_available:
        for (regime_val, tier_val), grp in df.groupby(["regime", "tier"], sort=True):
            lbl = f"regime_{regime_val}_tier_{tier_val}"
            frame = _build_one(grp, label=lbl, regime=str(regime_val), tier=str(tier_val))
            if not frame.empty:
                all_long_frames.append(frame)

    # ── 7. Write consolidated long-form output ───────────────────────────────
    if all_long_frames:
        consolidated = pd.concat(all_long_frames, ignore_index=True)
        consolidated.to_csv(
            output_dir / f"transition_matrix_consolidated_{stamp}.csv",
            index=False,
            float_format="%.8f",
        )
        consolidated.to_csv(
            output_dir / "transition_matrix_consolidated_latest.csv",
            index=False,
            float_format="%.8f",
        )
        # Alias expected by intelligent_orchestrator.py health check (existence + size only)
        consolidated.to_csv(
            output_dir / "actuarial_phase_transition_matrix_latest.csv",
            index=False,
            float_format="%.8f",
        )

    # ── 8. Metadata ──────────────────────────────────────────────────────────
    phase_states = sorted(df["phase_current"].unique().tolist())
    regime_states = sorted(df["regime"].unique().tolist()) if regime_available else ["ALL"]
    tier_states = sorted(df["tier"].unique().tolist()) if tier_available else ["ALL"]

    meta = {
        "builder": "build_phase_transition_matrix.py",
        "version": "2.0.0",
        "built_at_local": datetime.now().isoformat(timespec="seconds"),
        "source_actuarial_database": str(actuarial_db),
        "source_size_bytes": actuarial_db.stat().st_size,
        "source_last_write": datetime.fromtimestamp(
            actuarial_db.stat().st_mtime
        ).isoformat(timespec="seconds"),
        "phase_column": phase_column,
        "regime_column": regime_column if regime_available else None,
        "tier_column": tier_column if tier_available else None,
        "fallback_columns": list(fallback_columns),
        "input_rows": _parquet_row_count(actuarial_db),
        "usable_transition_rows": usable_rows,
        "phase_states": phase_states,
        "regime_states": regime_states,
        "tier_states": tier_states,
        "favourable_next_phases": sorted(FAVOURABLE_NEXT_PHASES),
        "min_cell_count_threshold": MIN_CELL_COUNT,
        "sparse_cell_warnings": sparse_warnings,
        "sparse_cell_count": len(sparse_warnings),
        "stratification_levels_built": len(all_long_frames),
        "outputs": {
            "consolidated_long_form_latest": str(
                output_dir / "transition_matrix_consolidated_latest.csv"
            ),
            "output_directory": str(output_dir),
            "note": "Individual probability/count CSVs written per stratification level",
        },
    }

    meta_path = output_dir / f"transition_matrix_meta_{stamp}.json"
    latest_meta_path = output_dir / "transition_matrix_meta_latest.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    latest_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Summary to console
    print(f"\n[OK] Transition matrix build complete")
    print(f"     Usable transition rows : {usable_rows:,}")
    print(f"     Phase states           : {phase_states}")
    print(f"     Regime states          : {regime_states}")
    print(f"     Tier states            : {tier_states}")
    print(f"     Sparse cell warnings   : {len(sparse_warnings)}")
    print(f"     Output directory       : {output_dir}")

    if sparse_warnings:
        print(f"\n[WARN] {len(sparse_warnings)} sparse cells (< {MIN_CELL_COUNT} obs) — "
              f"treat their probabilities with caution:")
        for w in sparse_warnings[:10]:
            print(f"       {w['stratification']} | phase={w['phase_current']} | "
                  f"obs={w['total_observations']}")
        if len(sparse_warnings) > 10:
            print(f"       ... and {len(sparse_warnings) - 10} more (see meta JSON)")

    return meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build stratified actuarial phase-transition matrices."
    )
    parser.add_argument(
        "--actuarial-db", required=True,
        help="Path to the governed actuarial database (currently v7)",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Directory for transition matrix artifacts",
    )
    parser.add_argument(
        "--phase-column", default="phase_v2",
        help="Primary phase column (default: phase_v2)",
    )
    parser.add_argument(
        "--regime-column", default="macro_regime",
        help="Regime stratification column (default: macro_regime)",
    )
    parser.add_argument(
        "--tier-column", default="future_momentum_bucket",
        help="Tier stratification column (default: future_momentum_bucket)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate source/schema without writing outputs",
    )
    args = parser.parse_args()

    actuarial_db = Path(args.actuarial_db)
    output_dir = Path(args.output_dir)

    if args.dry_run:
        columns = _available_columns(actuarial_db)
        required = {"ticker", "date", args.phase_column}
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"Actuarial database missing required columns: {missing}")
        result = {
            "ok": True,
            "source_actuarial_database": str(actuarial_db),
            "source_size_bytes": actuarial_db.stat().st_size,
            "input_rows": _parquet_row_count(actuarial_db),
            "phase_column": args.phase_column,
            "regime_column_present": args.regime_column in columns,
            "tier_column_present": args.tier_column in columns,
        }
        print(json.dumps(result, indent=2))
        return 0

    meta = build_transition_matrix(
        actuarial_db,
        output_dir,
        phase_column=args.phase_column,
        regime_column=args.regime_column,
        tier_column=args.tier_column,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
