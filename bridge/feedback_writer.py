from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


def build_feedback(outcomes_db: Path) -> Dict[str, dict]:
    with sqlite3.connect(outcomes_db) as conn:
        rows = conn.execute(
            """
            SELECT state_key_6dim,
                   COUNT(*) AS n_live,
                   AVG(CASE WHEN thesis_validated = 'Y' THEN 1.0 ELSE 0.0 END) AS win_rate_live,
                   AVG(pnl_r_multiple) AS avg_r_live,
                   MAX(closed_at_utc) AS last_session_date
            FROM outcomes
            WHERE COALESCE(state_key_6dim, '') <> ''
            GROUP BY state_key_6dim
            """
        ).fetchall()
    return {
        key: {
            "n_live": int(n_live or 0),
            "win_rate_live": float(win_rate or 0.0),
            "avg_r_live": float(avg_r or 0.0),
            "last_session_date": last_session_date,
            "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        for key, n_live, win_rate, avg_r, last_session_date in rows
    }


def write_feedback(outcomes_db: Path, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(build_feedback(outcomes_db), indent=2, sort_keys=True), encoding="utf-8")
    return output_path

