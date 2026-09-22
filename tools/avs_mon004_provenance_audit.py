"""Read-only exact-contract provenance audit for MON-004 outcome research.

Raw Phantom snapshots are deliberately reported, never returned as governed
outcome observations. A backfill audit proves a request occurred, not the
identity or immutable content of any individual option row.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT
from canonical_data.phantom_outcome_source import (
    PhantomOutcomeProvenanceError,
    PhantomOutcomeSourceReader,
)
from tools.avs_mon004_canary import _sample_assessments, connect_read_only


VERIFIED = "VERIFIED_CANONICAL_REVISION"
UNVERSIONED = "UNVERSIONED_SNAPSHOT_RESEARCH_ONLY"
NO_QUOTE = "NO_EXACT_CONTRACT_QUOTE"
NOT_ELIGIBLE = "REVISION_NOT_AVAILABLE_AT_CUTOFF"
CONFLICT = "PROVENANCE_CONFLICT_FAIL_CLOSED"


def classify_session(
    phantom: sqlite3.Connection, *, ticker: str, contract_symbol: str,
    session: date, verified: bool,
) -> str:
    """Classify coverage without promoting a raw snapshot to authority."""
    if verified:
        return VERIFIED
    key = (ticker, session.isoformat(), contract_symbol)
    revision = phantom.execute(
        """SELECT 1 FROM canonical_option_chain_revisions
        WHERE ticker=? AND quote_date=? AND option_symbol=? LIMIT 1""", key,
    ).fetchone()
    if revision:
        return NOT_ELIGIBLE
    snapshot = phantom.execute(
        """SELECT 1 FROM chain_snapshots
        WHERE ticker=? AND quote_date=? AND option_symbol=? LIMIT 1""", key,
    ).fetchone()
    return UNVERSIONED if snapshot else NO_QUOTE


def audit(control_path: Path, price_path: Path, phantom_path: Path) -> dict:
    now = datetime.now(timezone.utc)
    control = connect_read_only(control_path)
    prices = connect_read_only(price_path)
    phantom = connect_read_only(phantom_path)
    reader = PhantomOutcomeSourceReader(control_path, phantom_path)
    session_counts: Counter[str] = Counter()
    horizon_counts: dict[int, Counter[str]] = {1: Counter(), 5: Counter()}
    direction_counts: dict[str, Counter[str]] = {}
    sample_size = 0
    try:
        for item in _sample_assessments(control):
            origin = date.fromisoformat(item["origin_session_date"])
            sessions = tuple(date.fromisoformat(row[0]) for row in prices.execute(
                """SELECT trading_date FROM ohlcv_daily
                WHERE ticker=? AND trading_date>? AND bar_status='COMPLETE'
                  AND adjustment_convention=? AND observed_at<=?
                ORDER BY trading_date LIMIT 5""",
                (item["ticker"], origin.isoformat(), DEFAULT_ADJUSTMENT,
                 now.isoformat()),
            ))
            if not sessions:
                continue
            sample_size += 1
            try:
                verified = reader.read_sessions(
                    ticker=item["ticker"], contract_symbol=item["contract_symbol"],
                    sessions=sessions,
                    assessment_cutoff_utc=datetime.fromisoformat(
                        item["evidence_cutoff_utc"].replace("Z", "+00:00")
                    ),
                    evaluation_cutoff_utc=now,
                )
                verified_dates = {entry.observation.session_date for entry in verified}
                states = [classify_session(
                    phantom, ticker=item["ticker"],
                    contract_symbol=item["contract_symbol"], session=session,
                    verified=session in verified_dates,
                ) for session in sessions]
            except (PhantomOutcomeProvenanceError, ValueError, KeyError):
                states = [CONFLICT] * len(sessions)
            session_counts.update(states)
            direction = item["governed_direction"]
            direction_counts.setdefault(direction, Counter()).update(states)
            for horizon in (1, 5):
                if len(states) < horizon:
                    horizon_counts[horizon]["UNDERLYING_NOT_MATURE"] += 1
                elif all(state == VERIFIED for state in states[:horizon]):
                    horizon_counts[horizon]["FULL_VERIFIED_PATH"] += 1
                elif any(state == CONFLICT for state in states[:horizon]):
                    horizon_counts[horizon]["PROVENANCE_CONFLICT"] += 1
                elif any(state == UNVERSIONED for state in states[:horizon]):
                    horizon_counts[horizon]["RAW_ONLY_PATH"] += 1
                else:
                    horizon_counts[horizon]["INCOMPLETE_VERIFIED_PATH"] += 1
        return {
            "as_of_utc": now.isoformat(),
            "scope": "read-only, oldest/newest 20 CALL and PUT assessments",
            "assessment_count_with_future_underlying": sample_size,
            "session_classification": dict(session_counts),
            "by_direction": {key: dict(value) for key, value in direction_counts.items()},
            "by_horizon": {str(key): dict(value) for key, value in horizon_counts.items()},
            "authority": "Only VERIFIED_CANONICAL_REVISION can enter governed outcome capture; raw-only is research-only",
            "backfill_audit_limitation": "query-level OK/NO_DATA does not bind an exact option row to immutable provider content",
        }
    finally:
        control.close()
        prices.close()
        phantom.close()


if __name__ == "__main__":
    print(json.dumps(audit(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/canonical/historical_prices.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2, sort_keys=True))
