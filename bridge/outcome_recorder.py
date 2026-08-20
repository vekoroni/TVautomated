from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict


SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    ticker TEXT,
    state_key_6dim TEXT,
    state_key_9dim TEXT,
    pnl_r_multiple REAL,
    mae REAL,
    mfe REAL,
    days_held REAL,
    exit_reason TEXT,
    thesis_validated TEXT,
    closed_at_utc TEXT
);
"""


def init_db(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(SCHEMA)


def record_outcome(path: Path, outcome: Dict[str, Any]) -> None:
    init_db(path)
    if outcome.get("state_key_9dim") and len(str(outcome["state_key_9dim"]).split("|")) != 9:
        outcome = dict(outcome)
        outcome["state_key_9dim"] = ""
    fields = [
        "run_id", "ticker", "state_key_6dim", "state_key_9dim", "pnl_r_multiple",
        "mae", "mfe", "days_held", "exit_reason", "thesis_validated", "closed_at_utc",
    ]
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"INSERT INTO outcomes ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
            [outcome.get(field) for field in fields],
        )

