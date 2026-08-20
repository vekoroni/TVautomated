"""Independently verify an EV3 Stage EV-0 barrier sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


KEY = [
    "state_key",
    "direction",
    "horizon_sessions",
    "target_distance_fraction",
    "stop_distance_fraction",
    "calculation_version",
]
BASE_KEY = ["state_key", "direction", "horizon_sessions"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, baseline: Path | None = None) -> dict:
    path = path.resolve()
    audit_path = path.with_suffix(".audit.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    frame = pd.read_parquet(path)

    expected_rows = (
        frame["state_key"].nunique()
        * frame["direction"].nunique()
        * frame["horizon_sessions"].nunique()
        * frame["target_distance_fraction"].nunique()
        * frame["stop_distance_fraction"].nunique()
    )
    probability_error = (
        frame[["p_target_first", "p_stop_first", "p_timeout"]].sum(axis=1) - 1
    ).abs()
    count_error = (
        frame["target_count"]
        + frame["stop_count"]
        + frame["timeout_count"]
        + frame["ambiguous_count"]
        - frame["n_nominal"]
    ).abs()
    within_cell_n = frame.groupby(BASE_KEY, as_index=False)["n_nominal"].nunique()
    maturity = (
        frame.groupby(BASE_KEY, as_index=False)["n_nominal"]
        .first()
        .pivot(index=["state_key", "direction"], columns="horizon_sessions", values="n_nominal")
    )
    maturity_violations = int(((maturity[5] < maturity[10]) | (maturity[10] < maturity[20])).sum())

    result = {
        "status": "PASS",
        "path": str(path),
        "rows": len(frame),
        "expected_rows": int(expected_rows),
        "states": int(frame["state_key"].nunique()),
        "directions": sorted(frame["direction"].unique().tolist()),
        "horizons": sorted(int(value) for value in frame["horizon_sessions"].unique()),
        "duplicate_key_count": int(frame.duplicated(KEY).sum()),
        "probability_sum_max_error": float(probability_error.max()),
        "count_invariant_max_error": int(count_error.max()),
        "n_effective_exceeds_nominal": int((frame["n_effective"] > frame["n_nominal"]).sum()),
        "nonconstant_n_within_cell": int((within_cell_n["n_nominal"] != 1).sum()),
        "maturity_monotonic_violations": maturity_violations,
        "audit_status": audit.get("status"),
        "audit_hash_matches": _sha256(path) == audit.get("output_sha256"),
        "production_consumer_enabled": audit.get("production_consumer_enabled"),
        "source_adjusted": audit.get("source_adjusted"),
        "used_tickers": audit.get("used_tickers"),
    }

    if baseline is not None:
        baseline_frame = pd.read_parquet(baseline.resolve())
        baseline_maturity = (
            baseline_frame.groupby(BASE_KEY, as_index=False)["n_nominal"]
            .first()
            .pivot(index=["state_key", "direction"], columns="horizon_sessions", values="n_nominal")
        )
        result.update(
            twenty_day_changed_vs_baseline=int((maturity[20] != baseline_maturity[20]).sum()),
            five_day_total_gain_vs_baseline=int((maturity[5] - baseline_maturity[5]).sum()),
            ten_day_total_gain_vs_baseline=int((maturity[10] - baseline_maturity[10]).sum()),
        )

    failures = {
        "row_cartesian_coverage": len(frame) != expected_rows,
        "duplicate_keys": result["duplicate_key_count"] != 0,
        "probability_sum": result["probability_sum_max_error"] > 1e-9,
        "count_invariant": result["count_invariant_max_error"] != 0,
        "effective_n": result["n_effective_exceeds_nominal"] != 0,
        "cell_n_consistency": result["nonconstant_n_within_cell"] != 0,
        "maturity_monotonicity": maturity_violations != 0,
        "audit_status": result["audit_status"] != "PASS",
        "audit_hash": not result["audit_hash_matches"],
        "production_isolation": result["production_consumer_enabled"] is not False,
        "adjustment_policy": result["source_adjusted"] is not True,
    }
    if baseline is not None:
        failures.update(
            baseline_20d_changed=result["twenty_day_changed_vs_baseline"] != 0,
            baseline_5d_not_improved=result["five_day_total_gain_vs_baseline"] <= 0,
            baseline_10d_not_improved=result["ten_day_total_gain_vs_baseline"] <= 0,
        )
    result["failures"] = [name for name, failed in failures.items() if failed]
    result["status"] = "FAIL" if result["failures"] else "PASS"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    result = verify(args.artifact, args.baseline)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
