from __future__ import annotations

from datetime import date, datetime, timezone
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest

import pandas as pd

from canonical_data.contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetType,
)
from canonical_data.dynamic_options_bridge import (
    CanonicalDOIObservationBridge,
    PhantomDOIProjectionRepository,
    extract_contract_activity,
    extract_put_call_context,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    OpportunityAcquisitionState,
    OptionObservationKind,
    decide_observation_acquisition,
)


UTC = timezone.utc
SESSION = date(2026, 9, 9)
CUTOFF = datetime(2026, 9, 9, 21, 0, tzinfo=UTC)
CALL = "ABC261016C00100000"
PUT = "ABC261016P00100000"


def option_rows() -> list[dict[str, object]]:
    return [
        {
            "underlying": "ABC", "symbol": CALL, "right": "C",
            "strike": 100.0, "expiration_date": "2026-10-16", "dte": 37,
            "bid": 4.0, "ask": 4.4, "bid_size": 8, "ask_size": 9,
            "volume": 100, "open_interest": 1000, "implied_vol": 0.30,
            "delta": 0.50, "gamma": 0.02, "theta": -0.05, "vega": 0.10,
            "underlying_price": 100.0, "quote_timestamp_utc": "2026-09-09T20:00:00Z",
        },
        {
            "underlying": "ABC", "symbol": PUT, "right": "P",
            "strike": 100.0, "expiration_date": "2026-10-16", "dte": 37,
            "bid": 3.8, "ask": 4.2, "bid_size": 7, "ask_size": 10,
            "volume": 200, "open_interest": 500, "implied_vol": 0.40,
            "delta": -0.50, "gamma": 0.02, "theta": -0.05, "vega": 0.11,
            "underlying_price": 100.0, "quote_timestamp_utc": "2026-09-09T20:00:00Z",
        },
        {
            "underlying": "ABC", "symbol": "ABC261016C00105000", "right": "CALL",
            "strike": 105.0, "expiration_date": "2026-10-16", "dte": 37,
            "bid": 2.0, "ask": 2.4, "bid_size": None, "ask_size": None,
            "volume": 50, "open_interest": 500, "implied_vol": 0.32,
            "delta": 0.35, "underlying_price": 100.0,
            "quote_timestamp_utc": "2026-09-09T20:00:00Z",
        },
        {
            "underlying": "ABC", "symbol": "ABC261016P00105000", "right": "PUT",
            "strike": 105.0, "expiration_date": "2026-10-16", "dte": 37,
            "bid": 6.5, "ask": 7.0, "bid_size": 4, "ask_size": 4,
            "volume": 100, "open_interest": 250, "implied_vol": 0.42,
            "delta": -0.65, "underlying_price": 100.0,
            "quote_timestamp_utc": "2026-09-09T20:00:00Z",
        },
    ]


class DOIObservationBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry_path = self.root / "control_plane.sqlite"
        self.registry = CanonicalRegistry(self.registry_path)
        self.registry.initialise()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def register(
        self,
        *,
        dataset_type: DatasetType = DatasetType.OPTION_CHAIN,
        rows: object | None = None,
        as_of: datetime = datetime(2026, 9, 9, 20, 0, tzinfo=UTC),
        name: str = "chain.json",
        source_run_id: str = "RUN-1",
        scope: DataScope | None = None,
    ) -> DatasetRecord:
        payload = rows if rows is not None else option_rows()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / name
        path.write_bytes(encoded)
        content_hash = hashlib.sha256(encoded).hexdigest()
        dataset_id = hashlib.sha256(
            f"{dataset_type.value}|ABC|{SESSION}|{content_hash}".encode()
        ).hexdigest()
        record = DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=dataset_type,
            instrument_id="ABC",
            session_date=SESSION,
            scope=scope or DataScope(
                start_date=SESSION, end_date=SESSION, sides=("CALL", "PUT")
            ),
            provider="MARKETDATA",
            content_hash=content_hash,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(path),
            observed_at=as_of,
            as_of=as_of,
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="test-v1",
            source_run_id=source_run_id,
        )
        self.registry.register_dataset(record)
        return record

    def test_acquisition_policy_retains_every_opportunity(self) -> None:
        for state in OpportunityAcquisitionState:
            decision = decide_observation_acquisition(
                opportunity_state=state, canonical_evidence_available=False
            )
            self.assertTrue(decision.retain_opportunity)
            self.assertEqual(decision.decision_authority, "NONE")
        self.assertFalse(
            decide_observation_acquisition(
                opportunity_state="DORMANT", canonical_evidence_available=False
            ).should_fetch
        )
        self.assertFalse(
            decide_observation_acquisition(
                opportunity_state="THESIS_CONDITION_BREACHED",
                canonical_evidence_available=False,
            ).should_fetch
        )
        self.assertTrue(
            decide_observation_acquisition(
                opportunity_state="THESIS_DATA_INSUFFICIENT",
                canonical_evidence_available=False,
            ).should_fetch
        )
        self.assertTrue(
            decide_observation_acquisition(
                opportunity_state="DORMANT", canonical_evidence_available=False,
                underlying_reactivated=True,
            ).should_fetch
        )
        self.assertFalse(
            decide_observation_acquisition(
                opportunity_state="EXPIRED", canonical_evidence_available=False,
                manual_refresh=True,
            ).should_fetch
        )

    def test_completed_session_reuses_canonical_without_fetch(self) -> None:
        record = self.register()
        calls = 0
        def acquire() -> object:
            nonlocal calls
            calls += 1
            raise AssertionError("provider must not be called on canonical hit")
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        result = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind=OptionObservationKind.COMPLETED_SESSION,
            evidence_cutoff_utc=CUTOFF, acquire_missing=acquire,
        )
        self.assertEqual(result.dataset_id, record.dataset_id)
        self.assertEqual(result.resolution, "CANONICAL_REUSE")
        self.assertEqual(result.physical_fetch_count, 0)
        self.assertEqual(calls, 0)

    def test_completed_session_reuse_is_bound_to_required_scope(self) -> None:
        narrow = DataScope(
            start_date=SESSION, end_date=SESSION, dte_min=1, dte_max=30,
            sides=("CALL", "PUT"),
        )
        broad = DataScope(
            start_date=SESSION, end_date=SESSION, dte_min=1, dte_max=60,
            sides=("CALL", "PUT"),
        )
        self.register(scope=narrow)
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        result = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            required_scope=broad, opportunity_state="DORMANT",
        )
        self.assertFalse(result.available)
        self.assertIn("SUPPRESSED", result.resolution)

    def test_fetch_missing_once_for_identical_scope(self) -> None:
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        calls = 0
        class Result:
            dataset_id = None
            resolution = "PROVIDER_FETCH"
        def acquire() -> object:
            nonlocal calls
            calls += 1
            Result.dataset_id = self.register(name="fetched.json").dataset_id
            return Result()
        first = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            acquire_missing=acquire,
        )
        second = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            acquire_missing=acquire,
        )
        self.assertTrue(first.available and second.available)
        self.assertEqual(first.physical_fetch_count, 1)
        self.assertEqual(second.physical_fetch_count, 0)
        self.assertEqual(calls, 1)
        restarted = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        third = restarted.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            acquire_missing=lambda: self.fail("restart must reuse canonical data"),
        )
        self.assertTrue(third.available)
        self.assertEqual(third.physical_fetch_count, 0)

    def test_resolver_cache_hit_is_not_counted_as_a_physical_fetch(self) -> None:
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        record = self.register(name="resolver-hit.json")
        result = SimpleNamespace(dataset_id=record.dataset_id, resolution="EXACT_HIT")
        observation = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            manual_refresh=True, acquire_missing=lambda: result,
        )
        self.assertTrue(observation.available)
        self.assertEqual(observation.physical_fetch_count, 0)

    def test_provider_empty_counts_once_and_is_not_repeated(self) -> None:
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        calls = 0
        def acquire() -> object:
            nonlocal calls
            calls += 1
            return SimpleNamespace(dataset_id=None, resolution="PROVIDER_EMPTY")
        first = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            acquire_missing=acquire,
        )
        second = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
            acquire_missing=acquire,
        )
        self.assertEqual(first.resolution, "PROVIDER_EMPTY")
        self.assertEqual(first.physical_fetch_count, 1)
        self.assertEqual(second.resolution, "ACQUISITION_ALREADY_ATTEMPTED")
        self.assertEqual(second.physical_fetch_count, 0)
        self.assertEqual(calls, 1)

    def test_dormant_miss_suppresses_fetch_but_manual_refresh_allows_one(self) -> None:
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        calls = 0
        def acquire() -> Mapping[str, str]:
            nonlocal calls
            calls += 1
            return {"dataset_id": self.register(name="manual.json").dataset_id}
        dormant = bridge.resolve(
            ticker="ABC", session_date=SESSION, observation_kind="COMPLETED_SESSION",
            evidence_cutoff_utc=CUTOFF, opportunity_state="DORMANT",
            acquire_missing=acquire,
        )
        self.assertFalse(dormant.available)
        self.assertEqual(calls, 0)
        manual = bridge.resolve(
            ticker="ABC", session_date=SESSION, observation_kind="COMPLETED_SESSION",
            evidence_cutoff_utc=CUTOFF, opportunity_state="DORMANT",
            manual_refresh=True, acquire_missing=acquire,
        )
        self.assertTrue(manual.available)
        self.assertEqual(calls, 1)

    def test_morning_resolution_is_exact_contract_and_cutoff_bound(self) -> None:
        self.register(
            dataset_type=DatasetType.EXACT_OPTION_QUOTE,
            rows=option_rows()[0], name="exact.json",
        )
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        found = bridge.resolve(
            ticker="ABC", session_date=SESSION, observation_kind="MORNING",
            contract_symbol=CALL, evidence_cutoff_utc=CUTOFF,
        )
        missing = bridge.resolve(
            ticker="ABC", session_date=SESSION, observation_kind="MORNING",
            contract_symbol=PUT, evidence_cutoff_utc=CUTOFF,
            opportunity_state="DORMANT",
        )
        self.assertTrue(found.available)
        self.assertFalse(missing.available)
        self.assertIn("SUPPRESSED", missing.resolution)

    def test_contract_activity_preserves_nulls_and_does_not_invent_flow(self) -> None:
        frame = pd.DataFrame(option_rows())
        activity = extract_contract_activity(frame, CALL)
        self.assertAlmostEqual(activity.spread_fraction, 0.4 / 4.2)
        self.assertAlmostEqual(activity.volume_oi_turnover, 0.1)
        self.assertIsNone(activity.quote_update_rate)
        self.assertTrue(activity.snapshot_only)
        missing_sizes = extract_contract_activity(frame, "ABC261016C00105000")
        self.assertIsNone(missing_sizes.bid_size)
        self.assertIsNone(missing_sizes.ask_size)

    def test_scoped_pcr_is_chain_context_not_contract_property(self) -> None:
        frame = pd.DataFrame(option_rows())
        previous = frame.copy()
        previous.loc[_side(previous) == "PUT", "volume"] /= 2
        context = extract_put_call_context(
            frame, selected_contract_symbol=CALL, target_spot=105,
            previous_frame=previous,
        )
        self.assertAlmostEqual(context.total_volume_pcr, 2.0)
        self.assertAlmostEqual(context.total_oi_pcr, 0.5)
        self.assertAlmostEqual(context.expiry_volume_pcr, 2.0)
        self.assertAlmostEqual(context.target_region_volume_pcr, 2.0)
        self.assertAlmostEqual(context.total_volume_pcr_change, 1.0)
        self.assertAlmostEqual(context.put_call_iv_skew, 0.10)
        self.assertFalse(context.signed_order_flow_available)
        self.assertIsNone(context.premium_flow_imbalance)

    def test_bundle_lineage_uses_only_canonical_dataset_id(self) -> None:
        record = self.register()
        bridge = CanonicalDOIObservationBridge(registry_path=self.registry_path)
        observation = bridge.resolve(
            ticker="ABC", session_date=SESSION,
            observation_kind="COMPLETED_SESSION", evidence_cutoff_utc=CUTOFF,
        )
        bundle = bridge.build_bundle(
            observation, selected_contract_symbol=CALL, target_spot=105
        )
        self.assertEqual(bundle.input_dataset_ids, (record.dataset_id,))
        self.assertEqual(bundle.decision_authority, "NONE")
        self.assertIsNotNone(bundle.activity)
        self.assertIsNotNone(bundle.put_call_context)

    def test_phantom_projection_is_read_only_point_in_time_and_lineage_bound(self) -> None:
        record = self.register()
        phantom_path = self.root / "phantom.sqlite"
        with closing(sqlite3.connect(phantom_path)) as connection:
            connection.execute(
                """CREATE TABLE chain_snapshots(
                    ticker TEXT, quote_date TEXT, side TEXT, bid REAL, ask REAL,
                    volume REAL, open_interest REAL, iv REAL, delta REAL, dte REAL
                )"""
            )
            connection.executemany(
                "INSERT INTO chain_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                [
                    ("ABC", "2026-09-08", "CALL", 2.0, 2.2, 20, 100, .30, .50, 37),
                    ("ABC", "2026-09-07", "C", 1.0, 1.4, 10, 50, .32, .55, 36),
                    # Same-cutoff session is forbidden to prevent look-ahead.
                    ("ABC", "2026-09-09", "CALL", 9.0, 9.1, 999, 999, .10, .50, 37),
                ],
            )
            connection.commit()
        repository = PhantomDOIProjectionRepository(phantom_path, self.registry)
        projection = repository.project(
            canonical_dataset_id=record.dataset_id, ticker="ABC", side="CALL",
            evidence_cutoff_utc=CUTOFF, dte=37, delta=.50,
        )
        self.assertTrue(projection.available)
        self.assertEqual(projection.observation_count, 2)
        self.assertEqual(projection.session_count, 2)
        self.assertEqual(projection.canonical_dataset_id, record.dataset_id)
        self.assertEqual(projection.decision_authority, "NONE")

    def test_phantom_unavailable_is_explicit_and_nonfatal(self) -> None:
        record = self.register()
        repository = PhantomDOIProjectionRepository(
            self.root / "missing.sqlite", self.registry
        )
        projection = repository.project(
            canonical_dataset_id=record.dataset_id, ticker="ABC", side="PUT",
            evidence_cutoff_utc=CUTOFF,
        )
        self.assertFalse(projection.available)
        self.assertEqual(projection.applicability, "PHANTOM_UNAVAILABLE")
        self.assertIsNone(projection.median_spread_fraction)

    def test_phantom_rejects_unregistered_or_mismatched_raw_lineage(self) -> None:
        repository = PhantomDOIProjectionRepository(
            self.root / "missing.sqlite", self.registry
        )
        with self.assertRaisesRegex(ValueError, "registered canonical dataset"):
            repository.project(
                canonical_dataset_id="unknown", ticker="ABC", side="CALL",
                evidence_cutoff_utc=CUTOFF,
            )


def _side(frame: pd.DataFrame) -> pd.Series:
    return frame["right"].map(
        lambda value: "PUT" if str(value).upper() in {"P", "PUT"} else "CALL"
    )


if __name__ == "__main__":
    unittest.main()
