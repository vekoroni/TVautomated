"""CDS-1 contract, lifecycle, registry, ledger, and storage regression tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data import (  # noqa: E402
    AtomicPayloadStore,
    CanonicalDataGateway,
    CanonicalFeatureFlags,
    CanonicalRegistry,
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetRequest,
    DatasetType,
    LifecycleManager,
    LifecycleState,
    RequestLedger,
    RequestResolution,
    ResolutionKind,
    filter_rows_to_worklist,
    publish_discovery_outcomes,
    reconcile_stage_outcomes,
)
from canonical_data.errors import (  # noqa: E402
    CanonicalDataDisabled,
    DatasetValidationError,
    FetchNotAuthorised,
    IllegalLifecycleTransition,
    LifecycleConcurrencyError,
    PayloadConflictError,
    WorklistViolation,
)


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
SESSION = date(2026, 8, 21)


def make_request(
    scope: DataScope,
    *,
    ticker: str = "BP",
    stage: str = "CORE",
    freshness: int | None = 3600,
) -> DatasetRequest:
    return DatasetRequest(
        run_id="run-1",
        requesting_stage=stage,
        dataset_type=DatasetType.DAILY_OHLCV,
        instrument_id=ticker,
        session_date=SESSION,
        scope=scope,
        freshness_seconds=freshness,
        accepted_providers=("polygon",),
        adjustment_convention="SPLIT_ADJUSTED",
        schema_version="1",
    )


def make_record(
    scope: DataScope,
    *,
    dataset_id: str = "dataset-1",
    status: CompletenessStatus = CompletenessStatus.COMPLETE,
    as_of: datetime = NOW,
) -> DatasetRecord:
    return DatasetRecord(
        dataset_id=dataset_id,
        dataset_type=DatasetType.DAILY_OHLCV,
        instrument_id="bp",
        session_date=SESSION,
        scope=scope,
        provider="polygon",
        adjustment_convention="SPLIT_ADJUSTED",
        schema_version="1",
        content_hash="a" * 64,
        completeness_status=status,
        storage_uri="payloads/BP.json",
        observed_at=as_of,
        as_of=as_of,
        source_run_id="run-1",
    )


class CanonicalDataSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary.name)
        self.registry = CanonicalRegistry(self.temp_path / "control_plane.sqlite")
        self.registry.initialise()
        self.registry.register_run("run-1", "EVENING", SESSION)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_feature_flags_default_off_and_parse_explicit_environment(self) -> None:
        self.assertEqual(
            CanonicalFeatureFlags.from_environment({}), CanonicalFeatureFlags()
        )
        flags = CanonicalFeatureFlags.from_environment(
            {
                "AVSHUNTER_CANONICAL_DATA_ENABLED": "true",
                "AVSHUNTER_CANONICAL_WRITE_THROUGH": "1",
                "AVSHUNTER_STAGE_GATING_ENFORCED": "yes",
                "AVSHUNTER_CANONICAL_OFFLINE_REPLAY": "on",
                "AVSHUNTER_CDS2_OHLCV_MODE": "shadow",
            }
        )
        self.assertEqual(
            flags, CanonicalFeatureFlags(True, True, True, True, "SHADOW")
        )

    def test_scope_is_normalised_hash_stable_and_supports_coverage(self) -> None:
        stored = DataScope(
            start_date=date(2026, 7, 1), end_date=SESSION,
            fields=("volume", "close", "CLOSE"), sides=("put", "call"),
            dte_min=0, dte_max=60,
        )
        equivalent = DataScope.from_dict(stored.to_dict())
        requested = DataScope(
            start_date=date(2026, 8, 1), end_date=SESSION,
            fields=("close",), sides=("call",), dte_min=7, dte_max=30,
        )
        self.assertEqual(stored.fingerprint, equivalent.fingerprint)
        self.assertTrue(stored.covers(requested))
        self.assertTrue(stored.overlaps(requested))

    def test_registry_resolves_exact_superset_partial_and_stale_miss(self) -> None:
        narrow = DataScope(
            start_date=date(2026, 8, 1), end_date=SESSION, fields=("CLOSE",)
        )
        self.registry.register_dataset(make_record(narrow, dataset_id="exact"))
        self.assertIs(
            self.registry.resolve(make_request(narrow), now=NOW).kind,
            ResolutionKind.EXACT_HIT,
        )
        wide = DataScope(
            start_date=date(2026, 7, 1), end_date=SESSION,
            fields=("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"),
        )
        self.registry.register_dataset(make_record(wide, dataset_id="wide"))
        subset = DataScope(
            start_date=date(2026, 7, 15), end_date=SESSION,
            fields=("CLOSE", "VOLUME"),
        )
        self.assertIs(
            self.registry.resolve(make_request(subset), now=NOW).kind,
            ResolutionKind.SUPERSET_HIT,
        )
        extended = DataScope(
            start_date=date(2026, 6, 1), end_date=SESSION, fields=("CLOSE",)
        )
        self.assertIs(
            self.registry.resolve(make_request(extended), now=NOW).kind,
            ResolutionKind.PARTIAL_HIT,
        )
        self.assertIs(
            self.registry.resolve(
                make_request(narrow, freshness=60), now=NOW + timedelta(hours=2)
            ).kind,
            ResolutionKind.MISS,
        )

    def test_registry_schema_validates_and_supports_concurrent_clients(self) -> None:
        report = self.registry.validate_schema()
        self.assertTrue(report["valid"])
        self.assertEqual(report["missing_tables"], ())

        scope = DataScope(start_date=SESSION, end_date=SESSION, fields=("CLOSE",))

        def register(index: int) -> str:
            item = make_record(scope, dataset_id=f"concurrent-{index}")
            self.registry.register_dataset(item)
            restored = self.registry.get_dataset(item.dataset_id)
            return restored.dataset_id if restored else ""

        with ThreadPoolExecutor(max_workers=6) as executor:
            identifiers = tuple(executor.map(register, range(12)))
        self.assertEqual(set(identifiers), {f"concurrent-{i}" for i in range(12)})
        self.assertEqual(self.registry.dataset_count(), 12)

    def test_registry_preserves_provenance_and_content_identity(self) -> None:
        scope = DataScope(start_date=SESSION, end_date=SESSION, fields=("CLOSE",))
        self.registry.register_dataset(make_record(scope))
        restored = self.registry.get_dataset("dataset-1")
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.provider, "POLYGON")
        self.assertEqual(restored.content_hash, "a" * 64)
        self.assertEqual(restored.source_run_id, "run-1")
        self.assertEqual(restored.scope, scope)

        # AVS-SD-MON-003 item D (ACK, 20 Sep 2026): re-observing byte-identical content
        # (same dataset_id, since dataset_id is derived from content_hash) later, with a
        # different as_of, is the same object re-observed - not a conflict. Decision: keep
        # the first-observed record unchanged (idempotent no-op), discard the later as_of.
        later = make_record(scope, as_of=NOW + timedelta(minutes=1))
        self.registry.register_dataset(later)  # must not raise
        restored_again = self.registry.get_dataset("dataset-1")
        assert restored_again is not None
        self.assertEqual(restored_again.as_of, NOW)  # first-observed as_of, not the later one
        self.assertEqual(self.registry.dataset_count(), 1)

    def test_completeness_status_upgrade_on_identical_content_keeps_first_observed(self) -> None:
        # The motivating real-world case for item D: an option chain first registered PARTIAL
        # (early in a session) and later re-observed byte-identical and COMPLETE. Same
        # dataset_id/content_hash - this is one physical observation, not two.
        scope = DataScope(start_date=SESSION, end_date=SESSION, fields=("CLOSE",))
        partial = make_record(scope, status=CompletenessStatus.PARTIAL)
        self.registry.register_dataset(partial)

        upgraded = make_record(scope, status=CompletenessStatus.COMPLETE)
        self.registry.register_dataset(upgraded)  # must not raise "immutable and already registered"

        restored = self.registry.get_dataset("dataset-1")
        assert restored is not None
        self.assertEqual(restored.completeness_status, CompletenessStatus.PARTIAL)  # first-observed kept
        self.assertEqual(self.registry.dataset_count(), 1)

    def test_identical_dataset_is_reusable_across_runs_without_rewriting_origin(self) -> None:
        scope = DataScope(start_date=SESSION, end_date=SESSION, fields=("CLOSE",))
        original = make_record(scope)
        self.registry.register_dataset(original)

        repeated = replace(
            original,
            source_run_id="run-2",
            observed_at=original.observed_at + timedelta(minutes=5),
        )
        self.registry.register_dataset(repeated)

        restored = self.registry.get_dataset(original.dataset_id)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.source_run_id, "run-1")
        self.assertEqual(restored.observed_at, original.observed_at)
        self.assertEqual(self.registry.dataset_count(), 1)

        changed_content = replace(
            repeated,
            content_hash="b" * 64,
        )
        with self.assertRaises(DatasetValidationError):
            self.registry.register_dataset(changed_content)

    def test_lifecycle_blocks_drop_and_requires_explicit_reactivation(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        first = lifecycle.register(
            "run-1", "BP", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        active = lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_CORE, stage="CORE",
            expected_version=first.version,
        )
        self.assertTrue(lifecycle.authorise(
            "run-1", "CORE", "BP", DatasetType.DAILY_OHLCV
        ).authorised)
        dropped = lifecycle.transition(
            "run-1", "BP", LifecycleState.DROPPED_TERMINAL_LOGIC,
            stage="CORE", reason_code="EV_INELIGIBLE",
            expected_version=active.version,
        )
        self.assertFalse(lifecycle.authorise(
            "run-1", "CORE", "BP", DatasetType.DAILY_OHLCV
        ).authorised)
        with self.assertRaises(IllegalLifecycleTransition):
            lifecycle.transition(
                "run-1", "BP", LifecycleState.ACTIVE_DISCOVERY, stage="DISCOVERY"
            )
        reactivated = lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_DISCOVERY, stage="DISCOVERY",
            reason_code="MANUAL_REVIEW_APPROVED", expected_version=dropped.version,
            explicit_reactivation=True,
        )
        self.assertEqual(reactivated.version, dropped.version + 1)

    def test_lifecycle_rejects_stale_version_and_filters_worklist(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        bp = lifecycle.register(
            "run-1", "BP", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_CORE, stage="CORE",
            expected_version=bp.version,
        )
        xom = lifecycle.register(
            "run-1", "XOM", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "XOM", LifecycleState.DROPPED_TERMINAL_DATA,
            stage="DISCOVERY", reason_code="NO_PRICE_HISTORY",
            expected_version=xom.version,
        )
        self.assertEqual(
            lifecycle.create_worklist(
                "run-1", "CORE", DatasetType.DAILY_OHLCV, ("BP", "XOM")
            ),
            ("BP",),
        )
        self.assertEqual(lifecycle.worklist_counts("run-1"), {"CORE": 1})
        reconciliation = lifecycle.reconcile_worklist(
            "run-1", "CORE", DatasetType.DAILY_OHLCV, ("BP", "XOM")
        )
        self.assertTrue(reconciliation.reconciled)
        self.assertEqual(reconciliation.expected, ("BP",))
        with self.assertRaises(LifecycleConcurrencyError):
            lifecycle.transition(
                "run-1", "BP", LifecycleState.ACTIVE_OPTIONS,
                stage="OPTIONS", expected_version=1,
            )

    def test_request_ledger_separates_blocked_and_physical_requests(self) -> None:
        ledger = RequestLedger(self.registry)
        item = make_request(DataScope(fields=("CLOSE",)))
        ledger.record_blocked(item, "STATE_DROPPED_TERMINAL_LOGIC_BLOCKS_FETCH")
        request_id = ledger.start(item, provider="polygon")
        ledger.finish(
            request_id, RequestResolution.PROVIDER_FETCH,
            physical_request_count=1, retry_count=2,
        )
        entries = ledger.entries("run-1")
        self.assertEqual(entries[0]["resolution"], "BLOCKED_NOT_AUTHORISED")
        self.assertEqual(entries[0]["physical_request_count"], 0)
        self.assertEqual(ledger.physical_request_count("run-1"), 1)

    def test_atomic_store_reuses_identical_and_rejects_conflicts(self) -> None:
        store = AtomicPayloadStore(self.temp_path / "payloads")
        first = store.write_json("daily/BP.json", {"close": 41.0})
        second = store.write_json("daily/BP.json", {"close": 41.0})
        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertTrue(store.verify("daily/BP.json", first.content_hash))
        with self.assertRaises(PayloadConflictError):
            store.write_json("daily/BP.json", {"close": 42.0})
        with self.assertRaises(ValueError):
            store.write_json("../outside.json", {})

    def test_atomic_interruption_preserves_old_payload_and_cleans_temp(self) -> None:
        store = AtomicPayloadStore(self.temp_path / "payloads")
        original = store.write_bytes("daily/BP.bin", b"original")
        with patch("canonical_data.storage.os.replace", side_effect=OSError("stop")):
            with self.assertRaises(OSError):
                store.write_bytes("daily/BP.bin", b"replacement", overwrite=True)
        self.assertTrue(store.verify("daily/BP.bin", original.content_hash))
        self.assertEqual(list(original.path.parent.glob("*.tmp")), [])

    def test_parquet_promotion_checks_hash_and_is_atomic(self) -> None:
        store = AtomicPayloadStore(self.temp_path / "payloads")
        source = self.temp_path / "stage.parquet"
        source.write_bytes(b"PAR1-test-payload-PAR1")
        expected_hash = store.hash_bytes(source.read_bytes())
        promoted = store.promote_parquet(
            source, "daily/BP.parquet", expected_hash=expected_hash
        )
        self.assertTrue(store.verify("daily/BP.parquet", expected_hash))
        self.assertTrue(source.exists())
        self.assertEqual(promoted.content_hash, expected_hash)
        with self.assertRaises(ValueError):
            store.promote_parquet(source, "daily/BP.parquet", expected_hash="bad")

    def test_gateway_disabled_default_and_records_denied_request(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        ledger = RequestLedger(self.registry)
        item = make_request(DataScope(fields=("CLOSE",)))
        gateway = CanonicalDataGateway(self.registry, lifecycle, ledger)
        with self.assertRaises(CanonicalDataDisabled):
            gateway.resolve(item)
        enabled = CanonicalDataGateway(
            self.registry, lifecycle, ledger,
            flags=CanonicalFeatureFlags(enabled=True),
        )
        with self.assertRaises(FetchNotAuthorised):
            enabled.resolve(item)
        entries = ledger.entries("run-1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["resolution"], "BLOCKED_NOT_AUTHORISED")
        self.assertEqual(entries[0]["physical_request_count"], 0)

    def test_gateway_authorised_cache_has_zero_physical_requests(self) -> None:
        scope = DataScope(start_date=SESSION, end_date=SESSION, fields=("CLOSE",))
        self.registry.register_dataset(make_record(scope))
        lifecycle = LifecycleManager(self.registry)
        first = lifecycle.register(
            "run-1", "BP", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_CORE,
            stage="CORE", expected_version=first.version,
        )
        ledger = RequestLedger(self.registry)
        gateway = CanonicalDataGateway(
            self.registry, lifecycle, ledger,
            flags=CanonicalFeatureFlags(enabled=True),
        )
        resolution = gateway.resolve(make_request(scope, freshness=None))
        self.assertIs(resolution.kind, ResolutionKind.EXACT_HIT)
        self.assertEqual(ledger.physical_request_count("run-1"), 0)

    def test_gateway_cache_miss_is_not_counted_as_provider_fetch(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        first = lifecycle.register(
            "run-1", "BP", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_CORE,
            stage="CORE", expected_version=first.version,
        )
        ledger = RequestLedger(self.registry)
        gateway = CanonicalDataGateway(
            self.registry, lifecycle, ledger,
            flags=CanonicalFeatureFlags(enabled=True),
        )
        resolution = gateway.resolve(
            make_request(DataScope(fields=("CLOSE",)), freshness=None)
        )
        self.assertIs(resolution.kind, ResolutionKind.MISS)
        self.assertEqual(ledger.entries("run-1")[0]["resolution"], "CACHE_MISS")
        self.assertEqual(ledger.physical_request_count("run-1"), 0)

    def test_cds3_gateway_requires_persisted_stage_worklist_when_enforced(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        first = lifecycle.register(
            "run-1", "BP", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "BP", LifecycleState.ACTIVE_CORE,
            stage="CORE", expected_version=first.version,
        )
        ledger = RequestLedger(self.registry)
        gateway = CanonicalDataGateway(
            self.registry,
            lifecycle,
            ledger,
            flags=CanonicalFeatureFlags(enabled=True, stage_gating_enforced=True),
        )
        request = make_request(DataScope(fields=("CLOSE",)), freshness=None)

        with self.assertRaisesRegex(FetchNotAuthorised, "TICKER_NOT_IN_STAGE_WORKLIST"):
            gateway.resolve(request)
        self.assertEqual(ledger.entries("run-1")[0]["physical_request_count"], 0)

        lifecycle.create_worklist(
            "run-1", "CORE", DatasetType.DAILY_OHLCV, ("BP",)
        )
        resolution = gateway.resolve(request)
        self.assertIs(resolution.kind, ResolutionKind.MISS)
        self.assertEqual(ledger.physical_request_count("run-1"), 0)

    def test_cds3_dropped_sentinel_cannot_reenter_or_create_request(self) -> None:
        lifecycle = LifecycleManager(self.registry)
        first = lifecycle.register(
            "run-1", "SENTINEL", allowed_capabilities=(DatasetType.DAILY_OHLCV,)
        )
        lifecycle.transition(
            "run-1", "SENTINEL", LifecycleState.DROPPED_TERMINAL_LOGIC,
            stage="DISCOVERY", reason_code="TEST_DROP", expected_version=first.version,
        )
        self.assertEqual(
            lifecycle.create_worklist(
                "run-1", "DISCOVERY", DatasetType.DAILY_OHLCV, ("SENTINEL",)
            ),
            (),
        )
        ledger = RequestLedger(self.registry)
        gateway = CanonicalDataGateway(
            self.registry,
            lifecycle,
            ledger,
            flags=CanonicalFeatureFlags(enabled=True, stage_gating_enforced=True),
        )
        with self.assertRaises(FetchNotAuthorised):
            gateway.resolve(
                make_request(
                    DataScope(fields=("CLOSE",)),
                    ticker="SENTINEL",
                    stage="DISCOVERY",
                    freshness=None,
                )
            )
        self.assertEqual(ledger.physical_request_count("run-1"), 0)

    def test_cds3_stage_outcomes_and_join_boundary_fail_closed(self) -> None:
        result = reconcile_stage_outcomes(
            ("BP", "XOM", "BAD"),
            survivors=("BP",),
            drops=("XOM",),
            errors=("BAD",),
        )
        self.assertTrue(result.reconciled)
        self.assertEqual(result.counts, {"input": 3, "survivors": 1, "drops": 1, "errors": 1})
        with self.assertRaises(WorklistViolation):
            reconcile_stage_outcomes(
                ("BP", "XOM"), survivors=("BP",), drops=(), errors=()
            )
        with self.assertRaisesRegex(WorklistViolation, "absent from authorised worklist"):
            filter_rows_to_worklist(
                ({"ticker": "BP"}, {"ticker": "DROPPED"}),
                ("BP",),
            )

    def test_cds3_discovery_publication_is_reconciled_and_idempotent(self) -> None:
        rows = (
            {
                "ticker": "BP",
                "outcome": "SURVIVE",
                "lifecycle_state": "ACTIVE_CORE",
                "reason_code": "DISCOVERY_SURVIVOR",
            },
            {
                "ticker": "NO_DATA",
                "outcome": "DROP",
                "lifecycle_state": "DROPPED_TERMINAL_DATA",
                "reason_code": "NO_PRICE_DATA",
            },
            {
                "ticker": "NO_SIGNAL",
                "outcome": "DROP",
                "lifecycle_state": "DROPPED_STAGE",
                "reason_code": "NO_SIGNAL_AT_ANY_HORIZON",
            },
        )
        result = publish_discovery_outcomes(
            self.registry,
            run_id="discovery-run",
            session_date=SESSION,
            rows=rows,
        )
        self.assertEqual(
            result.as_dict(),
            {
                "run_id": "discovery-run",
                "input_count": 3,
                "survivor_count": 1,
                "drop_count": 2,
                "error_count": 0,
                "package_worklist_count": 1,
                "reconciled": True,
            },
        )
        lifecycle = LifecycleManager(self.registry)
        self.assertEqual(
            lifecycle.stage_worklist_tickers(
                "discovery-run", "PACKAGES", DatasetType.DAILY_OHLCV
            ),
            ("BP",),
        )
        self.assertEqual(
            lifecycle.latest("discovery-run", "NO_DATA").state,
            LifecycleState.DROPPED_TERMINAL_DATA,
        )

        repeated = publish_discovery_outcomes(
            self.registry,
            run_id="discovery-run",
            session_date=SESSION,
            rows=rows,
        )
        self.assertEqual(repeated.package_worklist_count, 1)
        self.assertEqual(lifecycle.latest("discovery-run", "BP").version, 2)

    def test_cds3_discovery_publication_rejects_unclassified_input(self) -> None:
        with self.assertRaisesRegex(WorklistViolation, "duplicate ticker"):
            publish_discovery_outcomes(
                self.registry,
                run_id="duplicate-run",
                session_date=SESSION,
                rows=(
                    {"ticker": "BP", "outcome": "SURVIVE"},
                    {"ticker": "BP", "outcome": "DROP"},
                ),
            )

    def test_cds3_orchestrator_shadow_publication_writes_run_report(self) -> None:
        import intelligent_orchestrator as orchestrator

        output_dir = self.temp_path / "output"
        runs_dir = output_dir / "runs"
        base_dir = self.temp_path / "repo"
        discovery_dir = runs_dir / "shadow-run" / "discovery"
        discovery_dir.mkdir(parents=True)
        source = discovery_dir / "discovery_lifecycle_shadow-run.csv"
        source.write_text(
            "ticker,outcome,lifecycle_state,reason_code\n"
            "BP,SURVIVE,ACTIVE_CORE,DISCOVERY_SURVIVOR\n"
            "DROP,DROP,DROPPED_STAGE,NO_SIGNAL_AT_ANY_HORIZON\n",
            encoding="utf-8",
        )
        candidate_source = (
            discovery_dir / "discovery_candidates_ultimate_shadow-run.csv"
        )
        candidate_source.write_text(
            "ticker,tier,composite_score\nBP,1,72.5\n",
            encoding="utf-8",
        )

        with (
            patch.object(orchestrator.cfg, "OUTPUT_DIR", output_dir),
            patch.object(orchestrator.cfg, "RUNS_DIR", runs_dir),
            patch.object(orchestrator.cfg, "BASE_DIR", base_dir),
        ):
            self.assertTrue(orchestrator.publish_cds3_discovery_worklist("shadow-run"))
            with patch.dict(
                "os.environ", {"AVSHUNTER_STAGE_GATING_ENFORCED": "0"}
            ):
                self.assertIsNone(
                    orchestrator.prepare_cds3_governed_package_input("shadow-run")
                )
            with patch.dict(
                "os.environ", {"AVSHUNTER_STAGE_GATING_ENFORCED": "1"}
            ):
                governed_path = orchestrator.prepare_cds3_governed_package_input(
                    "shadow-run"
                )
                self.assertIsNotNone(governed_path)
                self.assertEqual(
                    governed_path.read_text(encoding="utf-8").splitlines()[1],
                    "BP,1,72.5",
                )

        report_path = (
            runs_dir
            / "shadow-run"
            / "canonical"
            / "cds3_discovery_publication_shadow-run.json"
        )
        report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["reconciled"])
        self.assertEqual(report["mode"], "SHADOW")
        self.assertFalse(report["enforcement_enabled"])
        registry = CanonicalRegistry(base_dir / "data" / "canonical" / "control_plane.sqlite")
        lifecycle = LifecycleManager(registry)
        self.assertEqual(
            lifecycle.stage_worklist_tickers(
                "shadow-run", "PACKAGES", DatasetType.DAILY_OHLCV
            ),
            ("BP",),
        )


if __name__ == "__main__":
    unittest.main()
