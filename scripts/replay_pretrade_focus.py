"""Replay an advisory pre-open focus list from a frozen EOD candidate CSV.

This never rewrites a pipeline run, invokes a provider, or changes trade
authority.  It is intended for an already completed run whose Lab artefact
predates the focus projection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.pretrade_focus import (  # noqa: E402
    FOCUS_EXPORT_FIELDS,
    FOCUS_PRIMARY,
    project_pretrade_focus,
)


def _rank(row: dict[str, str]) -> tuple[float, str]:
    try:
        value = float(row.get("slate_rank") or "")
    except ValueError:
        value = math.inf
    return (value if math.isfinite(value) else math.inf, row.get("ticker") or "")


def replay(source: Path, destination: Path) -> dict[str, object]:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or destination.exists():
        raise FileExistsError(f"refusing to overwrite an existing file: {destination}")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "direction", "invalidation_state", "target_state"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"candidate CSV lacks required fields: {sorted(required - set(reader.fieldnames or ())) }")
        rows = list(reader)
    if not rows:
        raise ValueError("candidate CSV has no rows")

    projected = [(row, project_pretrade_focus(row)) for row in rows]
    focused = [{**row, **focus} for row, focus in projected if focus["pretrade_focus_lane"] == FOCUS_PRIMARY]
    focused.sort(key=_rank)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FOCUS_EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(focused)
    with source.open("rb") as handle:
        source_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    return {
        "source_sha256": source_sha256,
        "total_rows": len(rows),
        "primary_focus": len(focused),
        "contract_repair_watch": sum(focus["pretrade_focus_lane"] == "FOCUS_CONTRACT_REPAIR" for _, focus in projected),
        "calls": sum(row.get("direction") == "CALL" for row in focused),
        "puts": sum(row.get("direction") == "PUT" for row in focused),
        "destination": str(destination),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(replay(args.input, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
