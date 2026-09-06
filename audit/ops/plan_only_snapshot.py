"""AVS-FIX-001 Part G — prove `--plan-only` writes nothing.

    python audit/ops/plan_only_snapshot.py <snapshot.json>          # capture
    python audit/ops/plan_only_snapshot.py <snapshot.json> --compare # diff

AVS-IMP-FIX-001 binding rule 1 permits exactly one plan-only dispatch, "with a
filesystem snapshot diff proving no writes". This takes that snapshot: for
every path under the directories a run would write to, it records size and
mtime (not content, which would take minutes over ~15k files and prove nothing
extra — a write changes the mtime).

Covers the run outputs, the canonical store and its databases, the dropbox and
the packages, because those are where a dispatch that was not plan-only would
leave a trace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

WATCHED = [
    "data/output/runs",
    "data/output/run_plans",
    "data/canonical",
    "dropbox",
    "logs",
]


def snapshot() -> dict[str, list]:
    tree: dict[str, list] = {}
    for relative in WATCHED:
        root = REPO / relative
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
            except (OSError, PermissionError):
                # An unreadable path cannot be written by this process either;
                # recorded as such rather than silently dropped.
                tree[str(path.relative_to(REPO)).replace("\\", "/")] = ["UNREADABLE"]
                continue
            tree[str(path.relative_to(REPO)).replace("\\", "/")] = [
                stat.st_size, int(stat.st_mtime_ns)
            ]
    return tree


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    destination = Path(sys.argv[1])
    compare = "--compare" in sys.argv

    current = snapshot()
    if not compare:
        destination.write_text(json.dumps(current, indent=0), encoding="utf-8")
        print(f"captured {len(current)} files -> {destination}")
        return 0

    before = json.loads(destination.read_text(encoding="utf-8"))
    added = sorted(set(current) - set(before))
    removed = sorted(set(before) - set(current))
    modified = sorted(
        path for path in set(before) & set(current) if before[path] != current[path]
    )

    print(f"files before : {len(before)}")
    print(f"files after  : {len(current)}")
    print(f"added        : {len(added)}")
    print(f"removed      : {len(removed)}")
    print(f"modified     : {len(modified)}")
    for label, paths in (("ADDED", added), ("REMOVED", removed), ("MODIFIED", modified)):
        for path in paths[:40]:
            print(f"  {label}: {path}")
        if len(paths) > 40:
            print(f"  ... and {len(paths) - 40} more {label}")

    clean = not (added or removed or modified)
    print("SNAPSHOT DIFF EMPTY - no writes" if clean
          else "SNAPSHOT DIFF NOT EMPTY - the invocation wrote to disk")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
