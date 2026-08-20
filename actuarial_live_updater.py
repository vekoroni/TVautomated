from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


OVERLAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS actuarial_live_overlay (
    state_hash_6dim TEXT PRIMARY KEY,
    state_key_6dim TEXT,
    state_key_9dim TEXT,
    n_prior INTEGER,
    prior_win_rate_10d REAL,
    prior_ev_10d REAL,
    n_live INTEGER DEFAULT 0,
    live_win_rate_10d REAL,
    live_avg_r REAL,
    blended_win_rate_10d REAL,
    blend_weight_live REAL,
    live_data_quality TEXT,
    last_updated TEXT,
    sessions_observed INTEGER DEFAULT 0
);
"""


def state_hash(state_key_6dim: str) -> str:
    return hashlib.sha256(str(state_key_6dim).encode("utf-8")).hexdigest()[:16]


def live_quality(n_live: int) -> str:
    if n_live >= 50:
        return "HIGH"
    if n_live >= 10:
        return "MEDIUM"
    return "LOW"


def apply_feedback_signals(db_path: Path, feedback_path: Path, priors: Dict[str, Dict[str, Any]] | None = None) -> int:
    """Apply live feedback into an overlay table only; historical tables are untouched."""
    priors = priors or {}
    feedback = json.loads(Path(feedback_path).read_text(encoding="utf-8"))
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    updated = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute(OVERLAY_SCHEMA)
        for key, payload in feedback.items():
            prior = priors.get(key, {})
            n_prior = int(prior.get("n_prior", 0) or 0)
            prior_wr = float(prior.get("prior_win_rate_10d", 0.0) or 0.0)
            prior_ev = float(prior.get("prior_ev_10d", 0.0) or 0.0)
            n_live = int(payload.get("n_live", 0) or 0)
            live_wr = float(payload.get("win_rate_live", 0.0) or 0.0)
            live_avg_r = float(payload.get("avg_r_live", 0.0) or 0.0)
            denom = max(n_prior + n_live, 1)
            blended = ((n_prior * prior_wr) + (n_live * live_wr)) / denom
            blend_weight = n_live / denom
            conn.execute(
                """
                INSERT OR REPLACE INTO actuarial_live_overlay (
                    state_hash_6dim, state_key_6dim, state_key_9dim, n_prior,
                    prior_win_rate_10d, prior_ev_10d, n_live, live_win_rate_10d,
                    live_avg_r, blended_win_rate_10d, blend_weight_live,
                    live_data_quality, last_updated, sessions_observed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state_hash(key),
                    key,
                    payload.get("state_key_9dim", ""),
                    n_prior,
                    prior_wr,
                    prior_ev,
                    n_live,
                    live_wr,
                    live_avg_r,
                    blended,
                    blend_weight,
                    live_quality(n_live),
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    int(payload.get("sessions_observed", 1) or 1),
                ),
            )
            updated += 1
    return updated


def efficiency_report(db_path: Path, output_path: Path) -> Path:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT state_key_6dim, n_live, prior_win_rate_10d, live_win_rate_10d,
                   live_avg_r, blended_win_rate_10d, blend_weight_live, live_data_quality
            FROM actuarial_live_overlay
            """
        ).fetchall()
    report = []
    for row in rows:
        key, n_live, prior_wr, live_wr, live_avg_r, blended, weight, quality = row
        delta = (live_wr or 0.0) - (prior_wr or 0.0)
        flags = []
        if abs(delta) > 0.05:
            flags.append("DIVERGES_FROM_PRIOR_GT_5PP")
        if (n_live or 0) > 20 and (live_wr or 0.0) < 0.40:
            flags.append("UNDERPERFORMING_STATE")
        if quality == "HIGH" and delta > 0.05:
            flags.append("OUTPERFORMING_STATE")
        report.append({
            "state_key_6dim": key,
            "n_live": n_live,
            "prior_win_rate_10d": prior_wr,
            "live_win_rate_10d": live_wr,
            "live_avg_r": live_avg_r,
            "blended_win_rate_10d": blended,
            "blend_weight_live": weight,
            "live_data_quality": quality,
            "flags": flags,
        })
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
