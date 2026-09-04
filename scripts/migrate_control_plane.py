"""Explicit, backed-up CDS control-plane schema migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from canonical_data.registry import CanonicalRegistry
from scripts.release_baseline import sqlite_snapshot


def migrate(database: Path, backup: Path) -> dict[str, object]:
    database = database.resolve()
    backup = backup.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    if backup.exists():
        raise FileExistsError(f"refusing to overwrite migration backup: {backup}")

    backup_record = sqlite_snapshot(database, backup)
    registry = CanonicalRegistry(database)
    status_before = registry.migration_status()
    if status_before["required"]:
        registry.initialise(allow_migration=True)
    validation = registry.validate_schema()
    if not validation["valid"]:
        raise RuntimeError(f"post-migration schema validation failed: {validation}")
    return {
        "database": str(database),
        "backup": backup_record,
        "status_before": status_before,
        "migration_applied": bool(status_before["required"]),
        "post_migration": validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    if not arguments.apply:
        raise SystemExit("--apply is required for the explicit migration")
    print(json.dumps(migrate(arguments.database, arguments.backup), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
