"""Preserve verified pre-retention Polygon bars in a staged actuarial refresh.

The historical endpoint can move its earliest available date forward.  This
script refuses to splice two adjusted series unless their overlapping OHLC
prices agree; it never changes the live actuarial database or old source files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd


PRICE_COLUMNS = ("open", "high", "low", "close")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(old_dir: Path, staged_dir: Path) -> tuple[dict, dict, list[tuple[str, str, float]]]:
    old_manifest = json.loads((old_dir / "_source_manifest.json").read_text(encoding="utf-8"))
    staged_manifest = json.loads((staged_dir / "_source_manifest.json").read_text(encoding="utf-8"))
    if old_manifest.get("status") != "COMPLETE" or staged_manifest.get("status") != "COMPLETE":
        raise ValueError("both source manifests must be COMPLETE")
    if old_manifest.get("provider") != "Polygon" or staged_manifest.get("provider") != "Polygon":
        raise ValueError("both sources must be Polygon")
    if old_manifest.get("adjusted") is not True or staged_manifest.get("adjusted") is not True:
        raise ValueError("both sources must be adjusted daily bars")
    if old_dir.resolve() == staged_dir.resolve():
        raise ValueError("old and staged directories must differ")

    actions: list[tuple[str, str, float]] = []
    conflicts: list[str] = []
    for ticker, old_record in old_manifest["tickers"].items():
        old_file = old_dir / f"{ticker}.csv"
        if old_record.get("status") not in {"PERSISTED", "REUSED"} or not old_file.exists():
            continue
        staged_file = staged_dir / f"{ticker}.csv"
        if not staged_file.exists():
            if str(old_record.get("max_date", "")) >= "2026-09-01":
                conflicts.append(f"{ticker}: current source disappeared from fresh download")
            else:
                actions.append((ticker, "CARRY_HISTORICAL", 1.0))
            continue
        old = pd.read_csv(old_file)
        fresh = pd.read_csv(staged_file)
        if old.empty or fresh.empty or old["date"].duplicated().any() or fresh["date"].duplicated().any():
            conflicts.append(f"{ticker}: empty or duplicate-date source")
            continue
        overlap = old.merge(fresh, on="date", suffixes=("_old", "_new"))
        if overlap.empty:
            conflicts.append(f"{ticker}: no overlapping dates")
            continue
        old_only = old.loc[~old["date"].isin(fresh["date"]), "date"]
        if not old_only.empty and old_only.max() >= fresh["date"].min():
            conflicts.append(f"{ticker}: old-only bars are not a pre-retention prefix")
            continue
        if not old_only.empty:
            # Only the adjacent overlap determines the adjustment needed for
            # older bars. Later overlap may contain legitimate provider
            # corrections or a split that happened after the prefix.
            boundary = overlap.sort_values("date").head(20)
            ratios = pd.concat(
                [boundary[f"{column}_new"] / boundary[f"{column}_old"]
                 for column in PRICE_COLUMNS], ignore_index=True
            )
            if ratios.isna().any() or not ratios.map(math.isfinite).all() or (ratios <= 0).any():
                conflicts.append(f"{ticker}: invalid boundary adjustment ratio")
                continue
            factor = float(ratios.median())
            if ((ratios / factor - 1).abs() > 0.0001).any():
                conflicts.append(f"{ticker}: inconsistent adjusted OHLC at retention boundary")
                continue
            volume_ratio = boundary["volume_new"] / boundary["volume_old"]
            valid_volume = volume_ratio.replace([float("inf"), -float("inf")], float("nan")).dropna()
            if not valid_volume.empty and ((valid_volume * factor - 1).abs() > 0.01).any():
                conflicts.append(f"{ticker}: volume does not confirm boundary adjustment")
                continue
            actions.append((ticker, "PREPEND", factor))
    if conflicts:
        raise ValueError(f"adjustment/coverage conflicts ({len(conflicts)}): {conflicts[:25]}")
    return old_manifest, staged_manifest, actions


def reconcile(old_dir: Path, staged_dir: Path) -> dict:
    old_manifest, staged_manifest, actions = check(old_dir, staged_dir)
    totals = {"PREPEND": 0, "CARRY_HISTORICAL": 0, "prefix_rows": 0}
    for ticker, action, factor in actions:
        old_file = old_dir / f"{ticker}.csv"
        staged_file = staged_dir / f"{ticker}.csv"
        old = pd.read_csv(old_file)
        if action == "PREPEND":
            fresh = pd.read_csv(staged_file)
            prefix = old.loc[old["date"].lt(fresh["date"].min())].copy()
            for column in PRICE_COLUMNS:
                prefix[column] *= factor
            prefix["volume"] /= factor
            combined = pd.concat([prefix, fresh], ignore_index=True).sort_values("date")
            totals["prefix_rows"] += len(prefix)
        else:
            combined = old
        temporary = staged_file.with_suffix(".csv.reconciling")
        combined.to_csv(temporary, index=False)
        os.replace(temporary, staged_file)
        record = staged_manifest["tickers"][ticker]
        record.update({
            "status": "REUSED" if action == "CARRY_HISTORICAL" else "PERSISTED",
            "rows": len(combined),
            "min_date": str(combined["date"].min()),
            "max_date": str(combined["date"].max()),
            "sha256": sha256(staged_file),
            "retained_prior_source_sha256": old_manifest["tickers"][ticker].get("sha256"),
            "retention_reconciliation": action,
            "retained_prefix_adjustment_factor": factor,
        })
        if action == "CARRY_HISTORICAL":
            record["stale_historical_only"] = True
        totals[action] += 1
    staged_manifest["prior_source_manifest"] = str((old_dir / "_source_manifest.json").resolve())
    staged_manifest["retention_reconciliation"] = totals
    manifest_path = staged_dir / "_source_manifest.json"
    temporary = manifest_path.with_suffix(".json.reconciling")
    temporary.write_text(json.dumps(staged_manifest, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-dir", type=Path, required=True)
    parser.add_argument("--staged-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    old_manifest, staged_manifest, actions = check(args.old_dir, args.staged_dir)
    plan = {"mode": "EXECUTE" if args.execute else "DRY_RUN", "old_tickers": len(old_manifest["tickers"]),
            "staged_tickers": len(staged_manifest["tickers"]),
            "prepend_tickers": sum(action == "PREPEND" for _, action, _ in actions),
            "carry_historical_tickers": sum(action == "CARRY_HISTORICAL" for _, action, _ in actions),
            "rebased_prefix_tickers": sum(action == "PREPEND" and abs(factor - 1) > 0.0001
                                          for _, action, factor in actions)}
    print(json.dumps(plan, indent=2), flush=True)
    if args.execute:
        print(json.dumps(reconcile(args.old_dir, args.staged_dir), indent=2), flush=True)


if __name__ == "__main__":
    main()
