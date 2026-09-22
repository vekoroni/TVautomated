"""Representative, isolated MON-004 batch writer canary.

All production databases are opened read-only. A bounded sample of genuine
families, assessments, canonical datasets and price bars is copied into
temporary SQLite stores; only those temporary stores receive outcome writes.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT, HistoricalPriceDatabase
from canonical_data.option_liquidity_lifecycle import OptionLiquidityLifecycleStore
from canonical_data.option_outcome_maturation import capture_matured_option_batch
from canonical_data.phantom_outcome_source import PhantomOutcomeSourceReader
from canonical_data.registry import CanonicalRegistry
from tools.avs_mon004_canary import connect_read_only
from tools.avs_mon004_writer_canary import _copy_rows


def select_families(control: sqlite3.Connection, *, per_direction: int) -> tuple[sqlite3.Row, ...]:
    """Oldest CALL/PUT families with assessments; deterministic but not random."""
    if per_direction < 1:
        raise ValueError("per_direction must be positive")
    rows = []
    for direction in ("CALL", "PUT"):
        rows.extend(control.execute(
            """SELECT f.family_id,f.ticker,f.governed_direction,f.run_id,
                      f.evidence_cutoff_utc
            FROM doi_contract_families AS f
            WHERE f.governed_direction=? AND EXISTS (
                SELECT 1 FROM doi_contract_assessments AS a
                WHERE a.family_id=f.family_id)
            ORDER BY f.evidence_cutoff_utc,f.family_id LIMIT ?""",
            (direction, per_direction),
        ).fetchall())
    return tuple(sorted(rows, key=lambda row: (row["evidence_cutoff_utc"], row["family_id"])))


def _copy_family_dependencies(
    control: sqlite3.Connection, prices: sqlite3.Connection,
    phantom: sqlite3.Connection, target_control: sqlite3.Connection,
    target_prices: sqlite3.Connection, family: sqlite3.Row,
) -> int:
    _copy_rows(control, target_control, "run_registry", "run_id=?", (family["run_id"],))
    assessments = control.execute(
        "SELECT * FROM doi_contract_assessments WHERE family_id=?",
        (family["family_id"],),
    ).fetchall()
    source_ids: set[str] = set()
    origin_ids = {row["observation_id"] for row in assessments}
    for observation_id in origin_ids:
        observation = control.execute(
            "SELECT * FROM option_contract_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        if observation is None:
            raise ValueError(f"missing origin observation {observation_id}")
        source_ids.add(observation["source_dataset_id"])
    for row in assessments:
        for revision in phantom.execute(
            """SELECT DISTINCT dataset_id FROM canonical_option_chain_revisions
            WHERE ticker=? AND option_symbol=? AND quote_date>?""",
            (family["ticker"], row["contract_symbol"],
             family["evidence_cutoff_utc"][:10]),
        ):
            source_ids.add(revision["dataset_id"])
    for dataset_id in source_ids:
        _copy_rows(control, target_control, "dataset_registry", "dataset_id=?",
                   (dataset_id,))
    for observation_id in origin_ids:
        _copy_rows(control, target_control, "option_contract_observations",
                   "observation_id=?", (observation_id,))
    _copy_rows(control, target_control, "doi_contract_families", "family_id=?",
               (family["family_id"],))
    for assessment in assessments:
        _copy_rows(control, target_control, "doi_contract_assessments",
                   "assessment_id=?", (assessment["assessment_id"],))
    bars = prices.execute(
        """SELECT * FROM ohlcv_daily WHERE ticker=? AND trading_date>?
          AND bar_status='COMPLETE' AND adjustment_convention=?
        ORDER BY trading_date LIMIT 20""",
        (family["ticker"], family["evidence_cutoff_utc"][:10],
         DEFAULT_ADJUSTMENT),
    ).fetchall()
    for batch_id in {row["current_batch_id"] for row in bars}:
        _copy_rows(prices, target_prices, "ohlcv_ingest_batches", "batch_id=?",
                   (batch_id,))
    for bar in bars:
        _copy_rows(prices, target_prices, "ohlcv_daily",
                   "ticker=? AND trading_date=? AND adjustment_convention=?",
                   (bar["ticker"], bar["trading_date"],
                    bar["adjustment_convention"]))
    return len(assessments)


def run_canary(
    control_path: Path, price_path: Path, phantom_path: Path,
    *, per_direction: int = 50,
) -> dict:
    if per_direction < 1 or per_direction > 100:
        raise ValueError("per_direction must be between 1 and 100")
    cutoff = datetime.now(timezone.utc)
    with closing(connect_read_only(control_path)) as control, \
            closing(connect_read_only(price_path)) as prices, \
            closing(connect_read_only(phantom_path)) as phantom:
        families = select_families(control, per_direction=per_direction)
        if not families:
            return {"status": "NO_ASSESSMENTS", "production_access": "read-only"}
        with tempfile.TemporaryDirectory(prefix="avs_mon004_batch_canary_") as directory:
            root = Path(directory)
            temp_control = root / "control.sqlite"
            temp_prices = root / "prices.sqlite"
            registry = CanonicalRegistry(temp_control)
            store = OptionLiquidityLifecycleStore(registry)
            store.initialise()
            price_store = HistoricalPriceDatabase(temp_prices)
            price_store.initialise()
            assessment_count = 0
            with registry.connection() as target_control, price_store.connection() as target_prices:
                for family in families:
                    assessment_count += _copy_family_dependencies(
                        control, prices, phantom, target_control,
                        target_prices, family,
                    )
                control_fk = target_control.execute("PRAGMA foreign_key_check").fetchall()
                price_fk = target_prices.execute("PRAGMA foreign_key_check").fetchall()
                if control_fk or price_fk:
                    raise RuntimeError(
                        f"dependency copy failed: control={len(control_fk)} price={len(price_fk)}"
                    )
            before = temp_control.stat().st_size
            reader = PhantomOutcomeSourceReader(temp_control, phantom_path)
            holder = sqlite3.connect(temp_control)
            holder.execute("BEGIN")
            holder.execute("SELECT COUNT(*) FROM doi_contract_families").fetchone()
            timings = []
            try:
                for scan_limit in (len(families) // 2, len(families), len(families)):
                    started = time.perf_counter()
                    summary = capture_matured_option_batch(
                        store, price_store, evaluation_cutoff_utc=cutoff,
                        current_run_id="MON004-ISOLATED-BATCH-CANARY",
                        candidate_scan_limit=scan_limit,
                        capture_limit=scan_limit,
                        horizons=(1, 5, 10, 20),
                        phantom_source_reader=reader,
                    )
                    timings.append((round(time.perf_counter() - started, 3), summary))
                wal_path = Path(str(temp_control) + "-wal")
                wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
            finally:
                holder.rollback()
                holder.close()
            with registry.connection() as target:
                sources = target.execute("SELECT COUNT(*) FROM doi_outcome_source_quotes").fetchone()[0]
                labels = target.execute("SELECT COUNT(*) FROM doi_outcome_labels").fetchone()[0]
                label_states = [tuple(row) for row in target.execute(
                    """SELECT horizon_sessions,data_status,COUNT(*)
                    FROM doi_outcome_labels GROUP BY horizon_sessions,data_status
                    ORDER BY horizon_sessions,data_status"""
                )]
                fk = target.execute("PRAGMA foreign_key_check").fetchall()
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if fk:
                raise RuntimeError(f"outcome writer foreign keys failed: {len(fk)}")
            if timings[-1][1].labels_appended:
                raise RuntimeError("replayed isolated batch appended duplicate labels")
            return {
                "status": "ISOLATED_BATCH_CANARY_COMPLETE",
                "production_access": "read-only; no full production database copy",
                "scope": "oldest CALL/PUT families; non-random operational sample",
                "families_copied": len(families),
                "assessments_copied": assessment_count,
                "directions": dict(Counter(row["governed_direction"] for row in families)),
                "batches": [dict(seconds=seconds, **summary.to_dict())
                            for seconds, summary in timings],
                "source_rows": sources,
                "outcome_labels": labels,
                "label_states": [
                    {"horizon_sessions": horizon, "data_status": status, "count": count}
                    for horizon, status, count in label_states
                ],
                "temp_control_growth_bytes": temp_control.stat().st_size - before,
                "temp_wal_bytes_before_checkpoint": wal_bytes,
                "foreign_key_errors": len(fk),
            }


if __name__ == "__main__":
    print(json.dumps(run_canary(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/canonical/historical_prices.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2, sort_keys=True))
