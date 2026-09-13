from __future__ import annotations

from datetime import date, datetime, timezone
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from canonical_data import (
    CanonicalMarketObservationResolver,
    CanonicalOptionChainService,
    CanonicalRegistry,
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetType,
    ProjectionDeliveryState,
    ProjectionOutbox,
    PhantomOptionChainProjector,
    deliver_phantom_option_events,
)
from domain.data_projection import (
    PHANTOM_OPTION_CHAIN_PROJECTION,
    canonical_dataset_committed,
)


SESSION = date(2026, 9, 11)
AS_OF = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)


def _record(tmp_path: Path, *, dataset_id: str = "dataset-1") -> DatasetRecord:
    payload = tmp_path / "chain.json"
    payload.write_text("[]", encoding="utf-8")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    return DatasetRecord(
        dataset_id=dataset_id,
        dataset_type=DatasetType.OPTION_CHAIN,
        instrument_id="SPY",
        session_date=SESSION,
        scope=DataScope(
            start_date=SESSION,
            end_date=SESSION,
            dte_min=1,
            dte_max=60,
            sides=("CALL", "PUT"),
        ),
        provider="MARKETDATA",
        content_hash=digest,
        completeness_status=CompletenessStatus.COMPLETE,
        storage_uri=str(payload),
        observed_at=AS_OF,
        as_of=AS_OF,
        adjustment_convention="RAW_OPTION_CONTRACT",
        schema_version="option_chain_v2",
        source_run_id="RUN-1",
    )


def test_projection_event_identity_is_deterministic_and_has_no_authority(tmp_path: Path) -> None:
    record = _record(tmp_path)
    first = canonical_dataset_committed(
        projection_name=PHANTOM_OPTION_CHAIN_PROJECTION,
        dataset_id=record.dataset_id,
        dataset_type=record.dataset_type.value,
        instrument_id=record.instrument_id,
        session_date=record.session_date,
        content_hash=record.content_hash,
        storage_uri=record.storage_uri,
        dataset_as_of_utc=record.as_of,
        source_run_id=record.source_run_id,
        created_at_utc=AS_OF,
    )
    second = canonical_dataset_committed(
        projection_name=PHANTOM_OPTION_CHAIN_PROJECTION,
        dataset_id=record.dataset_id,
        dataset_type=record.dataset_type.value,
        instrument_id=record.instrument_id,
        session_date=record.session_date,
        content_hash=record.content_hash,
        storage_uri=record.storage_uri,
        dataset_as_of_utc=record.as_of,
        source_run_id=record.source_run_id,
        created_at_utc=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    assert first.event_id == second.event_id
    assert first.to_dict()["execution_authority"] == "NONE"
    assert first.to_dict()["capital_authority"] == "NONE"


def test_dataset_and_projection_are_registered_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "control.sqlite"
    registry = CanonicalRegistry(database)
    registry.initialise()
    record = _record(tmp_path)
    registry.register_dataset(
        record, projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,)
    )
    registry.register_dataset(
        record, projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,)
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dataset_registry").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM projection_outbox").fetchone()[0] == 1
        state = connection.execute(
            "SELECT delivery_state FROM projection_outbox"
        ).fetchone()[0]
    assert state == ProjectionDeliveryState.PENDING.value


def test_outbox_enforces_delivery_transitions(tmp_path: Path) -> None:
    database = tmp_path / "control.sqlite"
    registry = CanonicalRegistry(database)
    registry.initialise()
    record = _record(tmp_path)
    registry.register_dataset(
        record, projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,)
    )
    outbox = ProjectionOutbox(database)
    event = outbox.events(
        projection_name=PHANTOM_OPTION_CHAIN_PROJECTION,
        states=(ProjectionDeliveryState.PENDING,),
    )[0]
    outbox.mark_processing(event.event_id)
    outbox.mark_failed(event.event_id, "temporary lock")
    outbox.mark_processing(event.event_id)
    outbox.mark_completed(event.event_id)
    with sqlite3.connect(database) as connection:
        state, attempts, error = connection.execute(
            "SELECT delivery_state, attempt_count, last_error FROM projection_outbox"
        ).fetchone()
    assert state == ProjectionDeliveryState.COMPLETED.value
    assert attempts == 2
    assert error == ""


def test_interrupted_projection_is_requeued_and_visible_in_health(tmp_path: Path) -> None:
    database = tmp_path / "control.sqlite"
    registry = CanonicalRegistry(database)
    registry.initialise()
    record = _record(tmp_path)
    registry.register_dataset(
        record, projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,)
    )
    outbox = ProjectionOutbox(database)
    event = outbox.events()[0]
    outbox.mark_processing(event.event_id)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE projection_outbox SET started_at_utc=? WHERE event_id=?",
            ("2020-01-01T00:00:00+00:00", event.event_id),
        )
    assert outbox.requeue_stale_processing(older_than_seconds=1) == 1
    health = outbox.health_summary()
    assert health["counts"]["FAILED_RETRYABLE"] == 1
    assert health["retryable_failures"][0]["event_id"] == event.event_id
    assert health["execution_authority"] == "NONE"
    assert health["capital_authority"] == "NONE"


def test_legacy_option_chain_service_emits_phantom_event(tmp_path: Path) -> None:
    service = CanonicalOptionChainService(
        registry_path=tmp_path / "control.sqlite",
        payload_root=tmp_path / "payloads",
        run_id="RUN-1",
        session_date=SESSION,
        dte_max=60,
        min_open_interest=0,
    )
    frame = pd.DataFrame(
        {
            "ticker": ["SPY"],
            "option_symbol": ["SPY260918C00770000"],
            "quote_timestamp_utc": [AS_OF.isoformat()],
        }
    )
    record = service._persist("SPY", frame, provider="MARKETDATA")
    events = ProjectionOutbox(tmp_path / "control.sqlite").events(
        projection_name=PHANTOM_OPTION_CHAIN_PROJECTION
    )
    assert len(events) == 1
    assert events[0].dataset_id == record.dataset_id


def test_v2_option_chain_json_persistence_emits_phantom_event(tmp_path: Path) -> None:
    resolver = CanonicalMarketObservationResolver(
        registry_path=tmp_path / "control.sqlite",
        payload_root=tmp_path / "payloads",
        run_id="RUN-2",
    )
    request = DatasetRequest(
        run_id="RUN-2",
        requesting_stage="OPTIONS",
        dataset_type=DatasetType.OPTION_CHAIN,
        instrument_id="QQQ",
        session_date=SESSION,
        scope=DataScope(start_date=SESSION, end_date=SESSION),
        accepted_providers=("MARKETDATA",),
        adjustment_convention="RAW_OPTION_CONTRACT",
        schema_version="option_chain_v2",
    )
    record = resolver._persist_json(
        request=request,
        payload=[{"ticker": "QQQ", "symbol": "QQQ260918P00700000"}],
        provider="MARKETDATA",
        as_of=AS_OF,
    )
    events = ProjectionOutbox(tmp_path / "control.sqlite").events()
    assert [event.dataset_id for event in events] == [record.dataset_id]


def test_invalid_immutable_reregistration_does_not_enqueue(tmp_path: Path) -> None:
    database = tmp_path / "control.sqlite"
    registry = CanonicalRegistry(database)
    registry.initialise()
    record = _record(tmp_path)
    registry.register_dataset(record)
    conflicting = replace(record, content_hash="different")
    with pytest.raises(Exception, match="immutable and already registered"):
        registry.register_dataset(
            conflicting,
            projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,),
        )
    with sqlite3.connect(database) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projection_outbox'"
        ).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM projection_outbox").fetchone()[0] if exists else 0
    assert count == 0


def _register_chain_revision(
    tmp_path: Path,
    *,
    dataset_id: str,
    bid: float,
    symbol: str = "SPY260918C00770000",
) -> tuple[Path, CanonicalRegistry]:
    database = tmp_path / "control.sqlite"
    payload = tmp_path / f"{dataset_id}.json"
    rows = [{
        "underlying": "SPY",
        "symbol": symbol,
        "right": "C",
        "strike": 770.0,
        "expiration_date": "2026-09-18",
        "dte": 7,
        "bid": bid,
        "ask": bid + 0.2,
        "bid_size": 10,
        "ask_size": 12,
        "open_interest": 100,
        "volume": 25,
        "implied_vol": 0.22,
        "delta": 0.51,
        "gamma": 0.03,
        "theta": -0.08,
        "vega": 0.11,
        "underlying_price": 770.0,
        "quote_timestamp_utc": AS_OF.isoformat(),
        "quote_source": "MARKETDATA",
    }]
    payload.write_text(
        json.dumps(rows, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    registry = CanonicalRegistry(database)
    registry.initialise()
    registry.register_dataset(
        DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="SPY",
            session_date=SESSION,
            scope=DataScope(
                start_date=SESSION,
                end_date=SESSION,
                dte_min=1,
                dte_max=60,
                sides=("CALL", "PUT"),
            ),
            provider="MARKETDATA",
            content_hash=digest,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(payload),
            observed_at=AS_OF,
            as_of=AS_OF,
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v2",
            source_run_id="RUN-1",
        ),
        projection_names=(PHANTOM_OPTION_CHAIN_PROJECTION,),
    )
    return database, registry


def test_phantom_projector_writes_history_compatibility_and_receipt(tmp_path: Path) -> None:
    database, _ = _register_chain_revision(
        tmp_path, dataset_id="chain-revision-1", bid=4.0
    )
    phantom = tmp_path / "phantom.db"
    event = ProjectionOutbox(database).events()[0]
    projector = PhantomOptionChainProjector(
        registry_path=database, phantom_database_path=phantom
    )
    first = projector.project(event)
    second = projector.project(event)
    assert first.rows_projected == 1
    assert first.already_projected is False
    assert second.already_projected is True
    with sqlite3.connect(phantom) as connection:
        current = connection.execute(
            "SELECT bid, ask, iv, source FROM chain_snapshots"
        ).fetchone()
        assert current == (4.0, 4.2, 0.22, "MARKETDATA")
        assert connection.execute(
            "SELECT COUNT(*) FROM canonical_option_chain_revisions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM canonical_projection_receipts"
        ).fetchone()[0] == 1


def test_provider_revision_is_appended_and_updates_current_read_model(tmp_path: Path) -> None:
    database, _ = _register_chain_revision(
        tmp_path, dataset_id="chain-revision-1", bid=4.0
    )
    _register_chain_revision(tmp_path, dataset_id="chain-revision-2", bid=5.0)
    phantom = tmp_path / "phantom.db"
    delivered = deliver_phantom_option_events(
        registry_path=database, phantom_database_path=phantom
    )
    assert len(delivered) == 2
    with sqlite3.connect(phantom) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM canonical_option_chain_revisions"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM chain_snapshots"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT bid FROM chain_snapshots"
        ).fetchone()[0] == 5.0
    with sqlite3.connect(database) as connection:
        states = connection.execute(
            "SELECT DISTINCT delivery_state FROM projection_outbox"
        ).fetchall()
    assert states == [(ProjectionDeliveryState.COMPLETED.value,)]


def test_projection_failure_is_retryable_and_does_not_partially_write(tmp_path: Path) -> None:
    database, registry = _register_chain_revision(
        tmp_path, dataset_id="chain-invalid", bid=4.0, symbol="SPY260918C00770000"
    )
    record = registry.get_dataset("chain-invalid")
    assert record is not None
    Path(record.storage_uri).write_text('[{"symbol":"BROKEN"}]', encoding="utf-8")
    phantom = tmp_path / "phantom.db"
    assert deliver_phantom_option_events(
        registry_path=database, phantom_database_path=phantom
    ) == ()
    with sqlite3.connect(database) as connection:
        state, error = connection.execute(
            "SELECT delivery_state, last_error FROM projection_outbox"
        ).fetchone()
    assert state == ProjectionDeliveryState.FAILED_RETRYABLE.value
    assert "content-hash verification" in error
    assert not phantom.exists()
