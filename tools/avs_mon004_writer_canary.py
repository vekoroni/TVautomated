"""Date-scoped outcome writer canary on a disposable, minimal real-data store.

Production control, price, and Phantom databases are opened read-only. Only
one assessment's dependency rows are copied into the temporary databases.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT, HistoricalPriceDatabase
from canonical_data.option_liquidity_lifecycle import OptionLiquidityLifecycleStore
from canonical_data.option_outcome_maturation import capture_matured_option_batch
from canonical_data.phantom_outcome_source import PhantomOutcomeSourceReader
from canonical_data.registry import CanonicalRegistry
from tools.avs_mon004_canary import _sample_assessments, connect_read_only


def _copy_rows(source: sqlite3.Connection, target: sqlite3.Connection,
               table: str, where: str, values: tuple) -> int:
    rows = source.execute(f"SELECT * FROM {table} WHERE {where}", values).fetchall()
    if not rows:
        return 0
    columns = rows[0].keys()
    target.executemany(
        f"INSERT OR IGNORE INTO {table}({','.join(columns)})"
        f" VALUES({','.join('?' for _ in columns)})",
        [tuple(row) for row in rows],
    )
    return len(rows)


def run_canary(control_path: Path, price_path: Path, phantom_path: Path) -> dict:
    now = datetime.now(timezone.utc)
    control = connect_read_only(control_path)
    prices = connect_read_only(price_path)
    reader = PhantomOutcomeSourceReader(control_path, phantom_path)
    try:
        selected = None
        for item in _sample_assessments(control):
            session_row = prices.execute(
                """SELECT * FROM ohlcv_daily WHERE ticker=? AND trading_date>?
                  AND bar_status='COMPLETE' AND adjustment_convention=?
                  AND observed_at<=? ORDER BY trading_date LIMIT 1""",
                (item["ticker"], item["origin_session_date"],
                 DEFAULT_ADJUSTMENT, now.isoformat()),
            ).fetchone()
            if session_row is None:
                continue
            session = date.fromisoformat(session_row["trading_date"])
            existing = control.execute(
                """SELECT COUNT(*) FROM option_contract_observations AS o
                JOIN dataset_registry AS d ON d.dataset_id=o.source_dataset_id
                WHERE o.ticker=? AND o.contract_symbol=? AND d.session_date=?
                  AND o.quote_as_of>? AND o.quote_as_of<=?
                  AND o.observed_at<=?""",
                (item["ticker"], item["contract_symbol"], session.isoformat(),
                 item["evidence_cutoff_utc"], now.isoformat(), now.isoformat()),
            ).fetchone()[0]
            if existing:
                continue
            verified = reader.read_sessions(
                ticker=item["ticker"], contract_symbol=item["contract_symbol"],
                sessions=(session,),
                assessment_cutoff_utc=datetime.fromisoformat(
                    item["evidence_cutoff_utc"].replace("Z", "+00:00")
                ), evaluation_cutoff_utc=now,
            )
            if verified:
                selected = (item, session_row, verified[0])
                break
        if selected is None:
            return {"status": "NO_REPRESENTATIVE_VERIFIED_GAP",
                    "production_access": "read-only"}
        item, bar, verified = selected
        assessment = control.execute(
            "SELECT * FROM doi_contract_assessments WHERE assessment_id=?",
            (item["assessment_id"],),
        ).fetchone()
        family = control.execute(
            "SELECT * FROM doi_contract_families WHERE family_id=?",
            (assessment["family_id"],),
        ).fetchone()
        origin = control.execute(
            "SELECT * FROM option_contract_observations WHERE observation_id=?",
            (assessment["observation_id"],),
        ).fetchone()
        with tempfile.TemporaryDirectory(prefix="avs_mon004_writer_") as directory:
            temp_control = Path(directory) / "control.sqlite"
            temp_prices = Path(directory) / "prices.sqlite"
            registry = CanonicalRegistry(temp_control)
            store = OptionLiquidityLifecycleStore(registry)
            store.initialise()
            price_store = HistoricalPriceDatabase(temp_prices)
            price_store.initialise()
            with registry.connection() as target:
                target.execute("PRAGMA foreign_keys=OFF")
                _copy_rows(control, target, "run_registry", "run_id=?",
                           (assessment["run_id"],))
                for dataset_id in {origin["source_dataset_id"],
                                   verified.observation.dataset_id}:
                    _copy_rows(control, target, "dataset_registry", "dataset_id=?",
                               (dataset_id,))
                _copy_rows(control, target, "option_contract_observations",
                           "observation_id=?", (origin["observation_id"],))
                _copy_rows(control, target, "doi_contract_families", "family_id=?",
                           (family["family_id"],))
                _copy_rows(control, target, "doi_contract_assessments",
                           "assessment_id=?", (assessment["assessment_id"],))
                target.execute("PRAGMA foreign_keys=ON")
                dependency_errors = target.execute("PRAGMA foreign_key_check").fetchall()
                if dependency_errors:
                    raise RuntimeError(f"isolated dependency copy failed: {dependency_errors[:3]}")
            with price_store.connection() as target:
                target.execute("PRAGMA foreign_keys=OFF")
                _copy_rows(prices, target, "ohlcv_ingest_batches", "batch_id=?",
                           (bar["current_batch_id"],))
                _copy_rows(prices, target, "ohlcv_daily",
                           "ticker=? AND trading_date=? AND adjustment_convention=?",
                           (bar["ticker"], bar["trading_date"],
                            bar["adjustment_convention"]))
                target.execute("PRAGMA foreign_keys=ON")
                if target.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("isolated price dependency copy failed")
            temp_reader = PhantomOutcomeSourceReader(temp_control, phantom_path)
            with registry.connection() as target:
                target.execute("PRAGMA journal_mode=WAL")
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before_bytes = temp_control.stat().st_size
            # Hold a read transaction so the temporary WAL cannot auto-truncate
            # before its write amplification has been measured.
            holder = sqlite3.connect(temp_control)
            holder.execute("BEGIN")
            holder.execute("SELECT COUNT(*) FROM doi_contract_families").fetchone()
            started = time.perf_counter()
            try:
                first = capture_matured_option_batch(
                    store, price_store, evaluation_cutoff_utc=now,
                    current_run_id="MON004-CANARY-RUN", candidate_scan_limit=1,
                    capture_limit=1, horizons=(1,),
                    phantom_source_reader=temp_reader,
                )
                first_seconds = time.perf_counter() - started
                wal_path = Path(str(temp_control) + "-wal")
                wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
            finally:
                holder.rollback()
                holder.close()
            started = time.perf_counter()
            second = capture_matured_option_batch(
                store, price_store, evaluation_cutoff_utc=now,
                current_run_id="MON004-CANARY-RUN", candidate_scan_limit=1,
                capture_limit=1, horizons=(1,),
                phantom_source_reader=temp_reader,
            )
            second_seconds = time.perf_counter() - started
            with registry.connection() as target:
                labels = target.execute("SELECT COUNT(*) FROM doi_outcome_labels").fetchone()[0]
                sources = target.execute(
                    "SELECT COUNT(*) FROM doi_outcome_source_quotes"
                ).fetchone()[0]
                dependencies = target.execute("PRAGMA foreign_key_check").fetchall()
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if dependencies:
                raise RuntimeError("isolated outcome writer violated foreign keys")
            return {
                "status": "ISOLATED_WRITER_CANARY_COMPLETE",
                "production_access": "read-only; no full database copy",
                "session_date": verified.observation.session_date.isoformat(),
                "direction": item["governed_direction"],
                "source_revision_id": verified.observation.observation_id,
                "first_batch": first.to_dict(),
                "second_batch": second.to_dict(),
                "source_rows": sources, "outcome_labels": labels,
                "first_capture_seconds": round(first_seconds, 4),
                "idempotent_replay_seconds": round(second_seconds, 4),
                "temp_control_growth_bytes": temp_control.stat().st_size - before_bytes,
                "temp_wal_bytes_before_checkpoint": wal_bytes,
                "foreign_key_errors": len(dependencies),
            }
    finally:
        control.close()
        prices.close()


if __name__ == "__main__":
    print(json.dumps(run_canary(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/canonical/historical_prices.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2))
