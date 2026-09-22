"""Read-only live DOI coverage probe plus isolated scheduler-index canary.

Never opens either production database for writing. The mini-store contains
only family scan keys and is deleted when the probe exits.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import statistics
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT


HORIZONS = (1, 5, 10, 20)
SAMPLE_PER_COHORT = 20


def connect_read_only(path: Path) -> sqlite3.Connection:
    path = path.resolve(strict=True)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True,
                                 timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def _scan_query(connection: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return connection.execute(
        """SELECT f.family_id,f.evidence_cutoff_utc
        FROM doi_contract_families AS f
        WHERE f.run_id <> ? AND f.evidence_cutoff_utc < ?
          AND EXISTS (SELECT 1 FROM doi_contract_assessments AS a
                      WHERE a.family_id=f.family_id)
        ORDER BY f.evidence_cutoff_utc,f.family_id LIMIT ?""",
        ("MON004-CANARY-NEVER-A-RUN", datetime.now(timezone.utc).isoformat(), limit),
    ).fetchall()


def _sample_assessments(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    found: dict[str, sqlite3.Row] = {}
    for direction in ("CALL", "PUT"):
        for order in ("ASC", "DESC"):
            rows = connection.execute(
                f"""SELECT a.assessment_id,a.contract_symbol,a.evidence_cutoff_utc,
                    f.ticker,f.governed_direction,o.quote_as_of,o.observed_at,
                    d.session_date AS origin_session_date
                FROM doi_contract_assessments AS a
                JOIN doi_contract_families AS f ON f.family_id=a.family_id
                JOIN option_contract_observations AS o
                    ON o.observation_id=a.observation_id
                JOIN dataset_registry AS d ON d.dataset_id=o.source_dataset_id
                WHERE f.governed_direction=?
                ORDER BY a.evidence_cutoff_utc {order},a.assessment_id {order}
                LIMIT ?""",
                (direction, SAMPLE_PER_COHORT),
            ).fetchall()
            for row in rows:
                found[row["assessment_id"]] = row
    return list(found.values())


def quote_coverage(
    control: sqlite3.Connection, prices: sqlite3.Connection,
    *, as_of_utc: str, phantom: sqlite3.Connection | None = None,
) -> dict:
    samples = _sample_assessments(control)
    buckets: dict[int, Counter[str]] = {h: Counter() for h in HORIZONS}
    phantom_buckets: dict[int, Counter[str]] = {h: Counter() for h in HORIZONS}
    by_direction: dict[str, Counter[str]] = {d: Counter() for d in ("CALL", "PUT")}
    origin_sessions: Counter[str] = Counter()
    for item in samples:
        origin_sessions[item["origin_session_date"]] += 1
        future_sessions = [row[0] for row in prices.execute(
            """SELECT trading_date FROM ohlcv_daily
            WHERE ticker=? AND trading_date>? AND bar_status='COMPLETE'
              AND adjustment_convention=? AND observed_at<=?
            ORDER BY trading_date LIMIT 20""",
            (item["ticker"], item["origin_session_date"],
             DEFAULT_ADJUSTMENT, as_of_utc),
        ).fetchall()]
        quote_rows = control.execute(
            """SELECT d.session_date,o.bid,o.ask
            FROM option_contract_observations AS o
            JOIN dataset_registry AS d ON d.dataset_id=o.source_dataset_id
            WHERE o.contract_symbol=? AND o.ticker=?
              AND d.session_date>? AND o.quote_as_of>?
              AND o.quote_as_of<=? AND o.observed_at<=?""",
            (item["contract_symbol"], item["ticker"],
             item["origin_session_date"], item["evidence_cutoff_utc"],
             as_of_utc, as_of_utc),
        ).fetchall()
        quote_sessions = {row[0] for row in quote_rows}
        two_sided_sessions = {
            row[0] for row in quote_rows
            if row[1] is not None and row[2] is not None
            and row[1] > 0 and row[2] >= row[1]
        }
        phantom_sessions: set[str] = set()
        phantom_two_sided_sessions: set[str] = set()
        if phantom is not None:
            for session in future_sessions:
                row = phantom.execute(
                    """SELECT bid,ask FROM chain_snapshots
                    WHERE ticker=? AND quote_date=? AND option_symbol=?""",
                    (item["ticker"], session, item["contract_symbol"]),
                ).fetchone()
                if row is None:
                    continue
                phantom_sessions.add(session)
                if (row[0] is not None and row[1] is not None
                        and row[0] > 0 and row[1] >= row[0]):
                    phantom_two_sided_sessions.add(session)
        by_direction[item["governed_direction"]]["sampled"] += 1
        for horizon in HORIZONS:
            if len(future_sessions) < horizon:
                buckets[horizon]["underlying_not_mature"] += 1
                if phantom is not None:
                    phantom_buckets[horizon]["underlying_not_mature"] += 1
                continue
            span = future_sessions[:horizon]
            if phantom is not None:
                phantom_raw = sum(session in phantom_sessions for session in span)
                phantom_two_sided = sum(
                    session in phantom_two_sided_sessions for session in span
                )
                for label, amount in (("observation", phantom_raw),
                                      ("two_sided", phantom_two_sided)):
                    level = "full" if amount == horizon else ("partial" if amount else "no")
                    phantom_buckets[horizon][f"{level}_exact_{label}_path"] += 1
            raw_matched = sum(session in quote_sessions for session in span)
            if raw_matched == horizon:
                buckets[horizon]["full_exact_observation_path"] += 1
            elif raw_matched:
                buckets[horizon]["partial_exact_observation_path"] += 1
            else:
                buckets[horizon]["no_exact_observation_path"] += 1
            matched = sum(session in two_sided_sessions for session in span)
            if matched == horizon:
                buckets[horizon]["full_exact_two_sided_path"] += 1
            elif matched:
                buckets[horizon]["partial_exact_two_sided_path"] += 1
            else:
                buckets[horizon]["no_exact_two_sided_path"] += 1
    return {
        "sample_count": len(samples),
        "sampling_method": "oldest/newest 20 assessments per CALL/PUT; overlapping IDs deduplicated",
        "origin_session_distribution": dict(sorted(origin_sessions.items())),
        "by_direction": {key: dict(value) for key, value in by_direction.items()},
        "by_horizon": {str(key): dict(value) for key, value in buckets.items()},
        "phantom_by_horizon": (
            {str(key): dict(value) for key, value in phantom_buckets.items()}
            if phantom is not None else None
        ),
        "caveat": "Non-random coverage probe, not a strategy-performance estimate; full means at least one registered exact-contract observation in every underlying session; two-sided additionally requires positive bid and non-crossed ask.",
    }


def isolated_index_probe(keys: list[tuple[str, str]]) -> dict:
    """Measure index/WAL bytes on a temporary key-only mini-store."""
    with tempfile.TemporaryDirectory(prefix="avs_mon004_canary_") as directory:
        path = Path(directory) / "families.sqlite"
        db = sqlite3.connect(path)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE doi_contract_families (family_id TEXT PRIMARY KEY, evidence_cutoff_utc TEXT NOT NULL)")
            db.executemany(
                "INSERT INTO doi_contract_families VALUES (?,?)", keys,
            )
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before = path.stat().st_size
            started = time.perf_counter()
            db.execute("CREATE INDEX idx_doi_outcome_scan_family ON doi_contract_families(evidence_cutoff_utc,family_id)")
            db.commit()
            index_seconds = time.perf_counter() - started
            wal_path = Path(str(path) + "-wal")
            peak_wal = wal_path.stat().st_size if wal_path.exists() else 0
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            after = path.stat().st_size
            return {
                "keys_copied": len(keys), "base_bytes": before,
                "index_growth_bytes": after - before,
                "index_build_wal_bytes_before_checkpoint": peak_wal,
                "index_build_seconds": round(index_seconds, 4),
                "scope": "isolated key-only mini-store; not a live control-plane index build",
            }
        finally:
            db.close()


def run_canary(control_path: Path, price_path: Path,
               phantom_path: Path | None = None) -> dict:
    control = connect_read_only(control_path)
    prices = connect_read_only(price_path)
    phantom = connect_read_only(phantom_path) if phantom_path else None
    try:
        entire_start = time.perf_counter()
        start = time.perf_counter()
        first = _scan_query(control)
        first_ms = (time.perf_counter() - start) * 1000
        timings = []
        for _ in range(5):
            start = time.perf_counter()
            _scan_query(control)
            timings.append((time.perf_counter() - start) * 1000)
        keys = [(row[0], row[1]) for row in control.execute(
            "SELECT family_id,evidence_cutoff_utc FROM doi_contract_families"
        )]
        now = datetime.now(timezone.utc).isoformat()
        size = control_path.stat().st_size
        free = shutil.disk_usage(control_path.parent).free
        coverage = quote_coverage(control, prices, as_of_utc=now, phantom=phantom)
        return {
            "as_of_utc": now,
            "production_access": "SQLite mode=ro + query_only; no production writes",
            "control_bytes": size,
            "disk_free_bytes": free,
            "families": len(keys),
            "assessments": _scalar(control, "SELECT COUNT(*) FROM doi_contract_assessments"),
            "labels": _scalar(control, "SELECT COUNT(*) FROM doi_outcome_labels"),
            "cursor_table_present": bool(control.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='doi_outcome_scan_cursor'"
            ).fetchone()),
            "scan_index_present": bool(control.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_doi_outcome_scan_family'"
            ).fetchone()),
            "live_read_scan": {
                "rows": len(first), "cold_ms": round(first_ms, 3),
                "warm_median_ms": round(statistics.median(timings), 3),
                "warm_max_ms": round(max(timings), 3),
            },
            "isolated_index": isolated_index_probe(keys),
            "quote_coverage": coverage,
            "total_probe_seconds": round(time.perf_counter() - entire_start, 3),
        }
    finally:
        control.close()
        prices.close()
        if phantom is not None:
            phantom.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path,
                        default=Path("data/canonical/control_plane.sqlite"))
    parser.add_argument("--prices", type=Path,
                        default=Path("data/canonical/historical_prices.sqlite"))
    parser.add_argument("--phantom", type=Path,
                        default=Path("data/phantom/phantom_history.db"))
    arguments = parser.parse_args()
    print(json.dumps(run_canary(arguments.control, arguments.prices,
                                arguments.phantom), indent=2))


if __name__ == "__main__":
    main()
