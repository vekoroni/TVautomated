"""Read the macro snapshot a run actually saw (read-only; never today's latest file)."""

from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT_NAME = "macro_snapshot.json"


def read_run_snapshot(runs_dir: Path, run_id: str) -> dict | None:
    path = runs_dir / run_id / SNAPSHOT_NAME
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
