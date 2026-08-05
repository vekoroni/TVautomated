#!/usr/bin/env python3
"""
Build the AVSHUNTER behaviour-state cache.

Reads the governed actuarial database or an enriched CSV/parquet in read-only mode
and writes a separate versioned behaviour cache. It refuses false precision by
excluding behaviour keys that still contain UNK dimensions unless explicitly
requested with --include-unk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from behaviour_state_builder import BEHAVIOUR_DIMS, build_behaviour_state_hash, is_precise_behaviour_state_key

DEFAULT_INPUT = Path(r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet")
DEFAULT_OUTPUT = Path(r"C:\Users\ACKVerissimo\vanguard\data\behaviour_cache_v7.parquet")
DEFAULT_AUDIT = Path(r"C:\Users\ACKVerissimo\vanguard\data\behaviour_cache_v7.audit.json")

SOURCE_ALIASES = {
    "phase": ["phase_v2", "wyckoff_phase_bucket", "wyckoff_phase", "phase"],
    "momentum": ["momentum_bucket", "momentum_tier"],
    "location": ["location_bucket", "control_state"],
    "trigger": ["trigger_state", "trigger_primary", "trigger_quality"],
    "horizon": ["horizon_bucket", "target_dte", "dte", "expected_holding_days"],
    "direction": ["direction", "primary_direction", "direction_bias", "trade_bias", "edge_direction", "trend_direction"],
    "catalyst": ["catalyst_overlay", "catalyst_state_overlay", "catalyst_proximity"],
}
OUTCOME_ALIASES = {
    "sample_count": ["ticker", "state_hash", "state_v2"],
    "selected_return": ["selected_return"],
    "selected_max_gain": ["selected_max_gain"],
    "selected_max_drawdown": ["selected_max_drawdown"],
    "selected_hit_target": ["selected_hit_target"],
    "avg_return_5d": ["outcome_5d_return", "return_5d", "avg_return_5d"],
    "avg_return_10d": ["outcome_10d_return", "return_10d", "avg_return_10d"],
    "avg_return_20d": ["outcome_20d_return", "return_20d", "avg_return_20d"],
    "avg_drawdown_5d": ["outcome_max_drawdown_5d", "max_drawdown_5d"],
    "avg_drawdown_10d": ["outcome_max_drawdown_10d", "max_drawdown_10d"],
    "avg_drawdown_20d": ["outcome_max_drawdown_20d", "max_drawdown_20d"],
    "hit_5pct_up_5d": ["outcome_hit_5pct_up_5d"],
    "hit_7pct_up_10d": ["outcome_hit_7pct_up_10d"],
    "hit_10pct_up": ["outcome_hit_10pct_up"],
}
MISSING = {"", "NAN", "NONE", "NULL", "NA", "N/A", "MISSING"}
DERIVED_TRIGGER_COLUMNS = {
    "phase_v2",
    "momentum_bucket",
    "location_bucket",
    "transition_flag_v2",
    "trend_direction",
    "structure_quality",
    "future_momentum_bucket",
    "momentum_delta",
}
DERIVED_HORIZON_COLUMNS = {
    "outcome_5d_return",
    "outcome_max_gain_5d",
    "outcome_max_drawdown_5d",
    "outcome_hit_5pct_up_5d",
    "outcome_10d_return",
    "outcome_max_gain_10d",
    "outcome_max_drawdown_10d",
    "outcome_hit_7pct_up_10d",
    "outcome_20d_return",
    "outcome_max_gain_20d",
    "outcome_max_drawdown_20d",
    "outcome_hit_10pct_up",
}
HORIZON_SPECS = {
    "SHORT": {
        "return": "outcome_5d_return",
        "max_gain": "outcome_max_gain_5d",
        "max_drawdown": "outcome_max_drawdown_5d",
        "hit_target": "outcome_hit_5pct_up_5d",
    },
    "MED": {
        "return": "outcome_10d_return",
        "max_gain": "outcome_max_gain_10d",
        "max_drawdown": "outcome_max_drawdown_10d",
        "hit_target": "outcome_hit_7pct_up_10d",
    },
    "LONG": {
        "return": "outcome_20d_return",
        "max_gain": "outcome_max_gain_20d",
        "max_drawdown": "outcome_max_drawdown_20d",
        "hit_target": "outcome_hit_10pct_up",
    },
}


def _available_columns(input_path: Path) -> list[str]:
    if input_path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        return list(pq.ParquetFile(input_path).schema.names)
    return list(pd.read_csv(input_path, nrows=0).columns)


def _first_existing(columns: Iterable[str], names: Iterable[str]) -> str | None:
    colset = set(columns)
    for name in names:
        if name in colset:
            return name
    return None


def _has_any(columns: Iterable[str], names: Iterable[str]) -> bool:
    return bool(set(columns).intersection(names))


def _source_row_count(input_path: Path) -> int:
    if input_path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        return int(pq.ParquetFile(input_path).metadata.num_rows)
    return int(sum(1 for _ in input_path.open("rb")) - 1)


def _read_source(input_path: Path) -> tuple[pd.DataFrame, list[str]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    all_cols = _available_columns(input_path)
    wanted = set()
    for aliases in list(SOURCE_ALIASES.values()) + list(OUTCOME_ALIASES.values()):
        found = _first_existing(all_cols, aliases)
        if found:
            wanted.add(found)
    wanted.update(c for c in DERIVED_TRIGGER_COLUMNS if c in all_cols)
    wanted.update(c for c in DERIVED_HORIZON_COLUMNS if c in all_cols)
    for extra in ["state_hash", "state_v2", "ticker"]:
        if extra in all_cols:
            wanted.add(extra)
    if input_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(input_path, columns=sorted(wanted))
    else:
        df = pd.read_csv(input_path, usecols=sorted(wanted), low_memory=False)
    return df, all_cols


def _norm_series(series: pd.Series, default: str = "UNK") -> pd.Series:
    out = series.astype("string").fillna("").str.strip().str.upper().str.replace(" ", "_", regex=False).str.replace("-", "_", regex=False)
    return out.mask(out.isin(MISSING), default).fillna(default)


def _derive_trigger_series(df: pd.DataFrame) -> pd.Series:
    """Backfill the controlled trigger dimension from v6 behaviour columns.

    The historical v6 DB predates explicit trigger_state. Sprint 2 therefore
    derives only two production-compatible trigger buckets:
    TRIGGER_EARLY_PROBE and NO_TRIGGER. This mirrors current Vanguard output
    without inventing unsupported breakout/reversal precision.
    """
    out = pd.Series(["NO_TRIGGER"] * len(df), index=df.index, dtype="string")
    if "transition_flag_v2" in df.columns:
        flag = pd.to_numeric(df["transition_flag_v2"], errors="coerce").fillna(0).ne(0)
        out = out.mask(flag, "TRIGGER_EARLY_PROBE")
    if "phase_v2" in df.columns:
        phase = _norm_series(df["phase_v2"])
        out = out.mask(phase.eq("EARLY_TRANSITION"), "TRIGGER_EARLY_PROBE")
    if {"momentum_bucket", "location_bucket"}.issubset(df.columns):
        momentum = _norm_series(df["momentum_bucket"])
        location = _norm_series(df["location_bucket"])
        pressure = momentum.isin(["HIGH", "EXTREME"]) & location.isin(["NEAR_HIGH", "NEAR_LOW"])
        out = out.mask(pressure, "TRIGGER_EARLY_PROBE")
    return out.fillna("NO_TRIGGER")


def _dim(df: pd.DataFrame, columns: list[str], dim: str) -> pd.Series:
    col = _first_existing(columns, SOURCE_ALIASES[dim])
    if not col or col not in df.columns:
        if dim == "trigger" and _has_any(df.columns, DERIVED_TRIGGER_COLUMNS):
            return _derive_trigger_series(df)
        return pd.Series(["UNK"] * len(df), index=df.index)
    raw = _norm_series(df[col], default="NONE" if dim == "catalyst" else "UNK")
    if dim == "horizon":
        mapped = raw.replace({"1_5D":"SHORT", "1_5":"SHORT", "0_7D":"SHORT", "6_10D":"MED", "6_10":"MED", "8_21D":"MED", "11_20D":"LONG", "11_20":"LONG", "22_PLUS":"LONG"})
        numeric = pd.to_numeric(raw, errors="coerce")
        mapped = mapped.mask(numeric.between(0, 7, inclusive="both").fillna(False), "SHORT")
        mapped = mapped.mask(numeric.between(8, 21, inclusive="both").fillna(False), "MED")
        mapped = mapped.mask(numeric.ge(22).fillna(False), "LONG")
        return mapped.fillna("UNK")
    if dim == "direction":
        return raw.replace({"CALL":"BULLISH", "BUY":"BULLISH", "BULL":"BULLISH", "UP":"BULLISH", "PUT":"BEARISH", "SELL":"BEARISH", "BEAR":"BEARISH", "DOWN":"BEARISH"})
    if dim == "catalyst":
        return raw.replace({"UNK":"NONE", "FAR":"NONE", "DATA_WEAK":"NONE", "WITHIN_7D":"NEAR", "TODAY":"ACTIVE", "PAST":"POST"})
    return raw


def _expand_missing_horizons(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, list[str], bool]:
    """Explode v6 rows into SHORT/MED/LONG records when no horizon column exists."""
    if _first_existing(columns, SOURCE_ALIASES["horizon"]):
        return df, columns, False
    if not _has_any(columns, DERIVED_HORIZON_COLUMNS):
        return df, columns, False

    frames = []
    for label, spec in HORIZON_SPECS.items():
        available = [c for c in spec.values() if c in df.columns]
        if not available:
            continue
        part = df.copy()
        part["horizon_bucket"] = label
        part["selected_return"] = pd.to_numeric(part.get(spec["return"]), errors="coerce") if spec["return"] in part else pd.NA
        part["selected_max_gain"] = pd.to_numeric(part.get(spec["max_gain"]), errors="coerce") if spec["max_gain"] in part else pd.NA
        part["selected_max_drawdown"] = pd.to_numeric(part.get(spec["max_drawdown"]), errors="coerce") if spec["max_drawdown"] in part else pd.NA
        part["selected_hit_target"] = pd.to_numeric(part.get(spec["hit_target"]), errors="coerce") if spec["hit_target"] in part else pd.NA
        frames.append(part)

    if not frames:
        return df, columns, False
    expanded = pd.concat(frames, ignore_index=True)
    expanded_columns = list(dict.fromkeys(list(columns) + ["horizon_bucket", "selected_return", "selected_max_gain", "selected_max_drawdown", "selected_hit_target"]))
    return expanded, expanded_columns, True


def _with_horizon_outcomes(df: pd.DataFrame, label: str, spec: dict[str, str]) -> pd.DataFrame:
    part = df.copy()
    part["horizon_bucket"] = label
    part["selected_return"] = pd.to_numeric(part.get(spec["return"]), errors="coerce") if spec["return"] in part else pd.NA
    part["selected_max_gain"] = pd.to_numeric(part.get(spec["max_gain"]), errors="coerce") if spec["max_gain"] in part else pd.NA
    part["selected_max_drawdown"] = pd.to_numeric(part.get(spec["max_drawdown"]), errors="coerce") if spec["max_drawdown"] in part else pd.NA
    part["selected_hit_target"] = pd.to_numeric(part.get(spec["hit_target"]), errors="coerce") if spec["hit_target"] in part else pd.NA
    return part


def _aggregate_cache_frame(enriched: pd.DataFrame, include_unk: bool) -> tuple[pd.DataFrame, int, dict[str, float]]:
    precise_mask = enriched["behaviour_state_precise"].fillna(False).astype(bool)
    precise_rows = int(precise_mask.sum())
    unk_audit = _unk_audit(enriched["behaviour_state_key"])
    if not include_unk:
        enriched = enriched[precise_mask].copy()
    group_cols = ["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay"]
    if len(enriched) == 0:
        cache = pd.DataFrame(columns=group_cols + ["sample_count", "cache_build_status"])
    else:
        cache = enriched.groupby(group_cols, dropna=False).agg(**_agg_spec(enriched, list(enriched.columns))).reset_index()
        cache["cache_build_status"] = "PRECISE_ONLY" if not include_unk else "INCLUDES_UNK"
    return cache, precise_rows, unk_audit


def _key_parts(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "phase": _dim(df, columns, "phase"),
        "momentum": _dim(df, columns, "momentum"),
        "location": _dim(df, columns, "location"),
        "trigger": _dim(df, columns, "trigger"),
        "horizon": _dim(df, columns, "horizon"),
        "direction": _dim(df, columns, "direction"),
        "catalyst": _dim(df, columns, "catalyst"),
    })


def _keys(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    parts = _key_parts(df, columns)
    key = parts.astype(str).agg("|".join, axis=1)
    return pd.DataFrame({
        "behaviour_state_key": key,
        "behaviour_state_hash": key.map(build_behaviour_state_hash),
        "behaviour_state_precise": key.map(is_precise_behaviour_state_key),
        "catalyst_overlay": parts["catalyst"],
    })


def _agg_spec(df: pd.DataFrame, columns: list[str]) -> dict[str, tuple[str, str]]:
    spec = {}
    for out_name, aliases in OUTCOME_ALIASES.items():
        col = _first_existing(columns, aliases)
        if col and col in df.columns:
            spec[out_name] = (col, "count" if out_name == "sample_count" else "mean")
    if "state_hash" in df.columns:
        spec["broad_state_count"] = ("state_hash", "nunique")
    return spec


def _unk_audit(keys: pd.Series) -> dict[str, float]:
    parts = keys.astype(str).str.split("|", expand=True)
    labels = ["phase", "momentum", "location", "trigger", "horizon", "direction", "catalyst"]
    return {label: round(float((parts[idx] == "UNK").mean() * 100.0), 2) for idx, label in enumerate(labels) if idx in parts.columns}


def _unk_audit_parts(parts: pd.DataFrame) -> dict[str, float]:
    return {
        label: round(float((parts[label].astype(str) == "UNK").mean() * 100.0), 2)
        for label in ["phase", "momentum", "location", "trigger", "horizon", "direction", "catalyst"]
        if label in parts.columns
    }


def _aggregate_horizon_part(part: pd.DataFrame, columns: list[str], include_unk: bool) -> tuple[pd.DataFrame, int, dict[str, float]]:
    parts = _key_parts(part, columns)
    unk_audit = _unk_audit_parts(parts)
    precise_mask = parts.ne("UNK").all(axis=1)
    precise_rows = int(precise_mask.sum())
    if not include_unk:
        part = part.loc[precise_mask].copy()
        parts = parts.loc[precise_mask].copy()

    group_cols = ["phase", "momentum", "location", "trigger", "horizon", "direction", "catalyst"]
    if len(part) == 0:
        return (
            pd.DataFrame(columns=["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay", "sample_count", "cache_build_status"]),
            precise_rows,
            unk_audit,
        )

    work = pd.concat([parts.reset_index(drop=True), part.reset_index(drop=True)], axis=1)
    agg: dict[str, tuple[str, str]] = {
        "sample_count": ("ticker", "count") if "ticker" in work.columns else ("phase", "count")
    }
    if "state_hash" in work.columns:
        agg["broad_state_count"] = ("state_hash", "nunique")
    for col in ("selected_return", "selected_max_gain", "selected_max_drawdown", "selected_hit_target"):
        if col in work.columns:
            agg[col] = (col, "mean")

    grouped = work.groupby(group_cols, dropna=False).agg(**agg).reset_index()
    grouped["behaviour_state_key"] = grouped[group_cols].astype(str).agg("|".join, axis=1)
    grouped["behaviour_state_hash"] = grouped["behaviour_state_key"].map(build_behaviour_state_hash)
    grouped["catalyst_overlay"] = grouped["catalyst"]
    grouped["cache_build_status"] = "PRECISE_ONLY" if not include_unk else "INCLUDES_UNK"
    ordered = ["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay"]
    ordered += [c for c in grouped.columns if c not in set(group_cols + ordered)]
    return grouped[ordered], precise_rows, unk_audit


def build_cache(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT, audit_path: Path = DEFAULT_AUDIT, include_unk: bool = False) -> pd.DataFrame:
    columns = _available_columns(input_path)
    missing_dimensions = {dim: _first_existing(columns, aliases) is None for dim, aliases in SOURCE_ALIASES.items()}
    derived_dimensions = {
        "trigger": missing_dimensions.get("trigger", False) and _has_any(columns, DERIVED_TRIGGER_COLUMNS),
        "horizon": missing_dimensions.get("horizon", False) and _has_any(columns, DERIVED_HORIZON_COLUMNS),
    }
    source_rows = _source_row_count(input_path)
    status_label = (
        "INCLUDES_UNK" if include_unk
        else "PRECISE_DERIVED_BACKFILL" if any(derived_dimensions.values())
        else "PRECISE_ONLY"
    )
    # False precision guard: every dimension must be sourced or reproducibly
    # derived. In particular, catalyst is a point-in-time overlay and must not
    # be defaulted to NONE when historical event data is absent.
    unresolved_dimensions = [
        dim for dim, missing in missing_dimensions.items()
        if missing and not derived_dimensions.get(dim, False)
    ]
    if not include_unk and unresolved_dimensions:
        cache = pd.DataFrame(columns=["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay", "sample_count", "cache_build_status"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cache.to_parquet(output_path, index=False)
        audit = {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "source_rows": int(source_rows),
            "cache_rows": 0,
            "unique_behaviour_hashes": 0,
            "include_unk": bool(include_unk),
            "unk_audit_source": {"trigger": 100.0 if missing_dimensions.get("trigger") else 0.0, "horizon": 100.0 if missing_dimensions.get("horizon") else 0.0},
            "precise_source_rows": 0,
            "missing_source_dimensions": missing_dimensions,
            "derived_source_dimensions": derived_dimensions,
            "cache_build_status": "EMPTY_SCHEMA_INSUFFICIENT_FOR_PRECISION",
            "unresolved_dimensions": unresolved_dimensions,
            "action_required": "Populate every unresolved point-in-time dimension from governed historical sources before enabling PRECISE_MATCH.",
        }
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
        return cache

    df, columns = _read_source(input_path)
    horizon_expanded = False
    if derived_dimensions.get("horizon") and not _first_existing(columns, SOURCE_ALIASES["horizon"]):
        cache_parts = []
        precise_rows = 0
        unk_audits: list[dict[str, float]] = []
        expanded_columns = list(dict.fromkeys(list(columns) + ["horizon_bucket", "selected_return", "selected_max_gain", "selected_max_drawdown", "selected_hit_target"]))
        for label, spec in HORIZON_SPECS.items():
            if not any(c in df.columns for c in spec.values()):
                continue
            part = _with_horizon_outcomes(df, label, spec)
            part_cache, part_precise_rows, part_unk = _aggregate_horizon_part(part, expanded_columns, include_unk)
            cache_parts.append(part_cache)
            precise_rows += part_precise_rows
            unk_audits.append(part_unk)
            del part
        horizon_expanded = bool(cache_parts)
        if cache_parts:
            cache = pd.concat(cache_parts, ignore_index=True)
            # Same key can appear in more than one chunk if source data had
            # unusual duplicate labels; collapse defensively.
            value_cols = [c for c in cache.columns if c not in {"behaviour_state_key", "behaviour_state_hash", "catalyst_overlay", "cache_build_status"}]
            agg = {c: ("sum" if c in {"sample_count"} else "mean") for c in value_cols}
            cache = cache.groupby(["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay"], dropna=False).agg(agg).reset_index()
            cache["cache_build_status"] = status_label
        else:
            cache = pd.DataFrame(columns=["behaviour_state_key", "behaviour_state_hash", "catalyst_overlay", "sample_count", "cache_build_status"])
        if unk_audits:
            unk_audit_source = {
                key: round(sum(a.get(key, 0.0) for a in unk_audits) / len(unk_audits), 2)
                for key in unk_audits[0]
            }
        else:
            unk_audit_source = {}
    else:
        key_df = _keys(df, columns)
        enriched = pd.concat([df.reset_index(drop=True), key_df], axis=1)
        cache, precise_rows, unk_audit_source = _aggregate_cache_frame(enriched, include_unk)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache.to_parquet(output_path, index=False)
    audit = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_rows": int(source_rows),
        "cache_rows": int(len(cache)),
        "unique_behaviour_hashes": int(cache["behaviour_state_hash"].nunique()) if "behaviour_state_hash" in cache else 0,
        "include_unk": bool(include_unk),
        "unk_audit_source": unk_audit_source,
        "precise_source_rows": precise_rows,
        "missing_source_dimensions": {dim: _first_existing(columns, aliases) is None for dim, aliases in SOURCE_ALIASES.items()},
        "derived_source_dimensions": derived_dimensions | {"horizon_expanded_from_outcomes": horizon_expanded},
        "cache_build_status": status_label,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    return cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AVSHUNTER behaviour-state cache")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--include-unk", action="store_true", help="Include incomplete UNK-heavy keys for diagnostics only")
    args = parser.parse_args()
    cache = build_cache(args.input, args.output, args.audit, args.include_unk)
    print(f"Behaviour cache written: {args.output}")
    print(f"Rows={len(cache)} unique_hashes={cache['behaviour_state_hash'].nunique() if 'behaviour_state_hash' in cache else 0}")
    print(f"Audit written: {args.audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
