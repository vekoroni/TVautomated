from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canonical_data.contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetType,
)
from canonical_data.errors import DatasetValidationError
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState,
    MonitorState,
    OptionLifecycleConcurrencyError,
    OptionLifecycleConflict,
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from canonical_data.registry import CanonicalRegistry
import morning_gate
from scripts import avshunter_options_intelligence as options_intelligence


RUN_ID = "20260829_180000"
SESSION = date(2026, 8, 29)
QUOTE_TIME = datetime(2026, 8, 29, 20, 0, tzinfo=timezone.utc)


class OptionLiquidityLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = CanonicalRegistry(self.root / "control_plane.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", SESSION)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _dataset(
        self,
        ticker: str = "BP",
        provider: str = "MARKETDATA",
        dataset_type: DatasetType = DatasetType.OPTION_CHAIN,
        suffix: str = "",
    ) -> str:
        dataset_id = f"chain-{ticker.lower()}-{provider.lower()}{suffix}"
        payload = self.root / f"{dataset_id}.parquet"
        payload.write_bytes(b"PAR1-test-PAR1")
        self.registry.register_dataset(
            DatasetRecord(
                dataset_id=dataset_id,
                dataset_type=dataset_type,
                instrument_id=ticker,
                session_date=SESSION,
                scope=DataScope(
                    start_date=SESSION,
                    end_date=SESSION,
                    dte_min=1,
                    dte_max=90,
                    sides=("CALL", "PUT"),
                ),
                provider=provider,
                content_hash="a" * 64,
                completeness_status=CompletenessStatus.COMPLETE,
                storage_uri=str(payload),
                observed_at=QUOTE_TIME,
                as_of=QUOTE_TIME,
                adjustment_convention="RAW_OPTION_CONTRACT",
                schema_version="option_chain_v1",
                source_run_id=RUN_ID,
            )
        )
        return dataset_id

    def _thesis(
        self,
        thesis_id: str = "BP-PUT-1",
        ticker: str = "BP",
        direction: str = "PUT",
    ):
        return self.store.record_thesis_event(
            thesis_id=thesis_id,
            event_key="EOD-CREATED",
            run_id=RUN_ID,
            ticker=ticker,
            direction=direction,
            thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE,
            reason_code="LIQUIDITY_PENDING",
            structural_target=38.0,
            invalidation_spot=43.0,
            horizon_end_date=date(2026, 9, 4),
        )

    def _observation(
        self,
        *,
        dataset_id: str,
        contract: str = "BP260918P00040000",
        quote_as_of: datetime = QUOTE_TIME,
        state: ContractLiquidityState = ContractLiquidityState.LIQUIDITY_PENDING,
        bid: float = 0.9,
        ask: float = 1.2,
    ):
        return self.store.record_contract_observation(
            thesis_id="BP-PUT-1",
            run_id=RUN_ID,
            ticker="BP",
            contract_symbol=contract,
            option_side="PUT",
            quote_as_of=quote_as_of,
            source_dataset_id=dataset_id,
            spot=41.0,
            strike=40.0,
            expiration=date(2026, 9, 18),
            dte=20,
            delta=-0.32,
            bid=bid,
            ask=ask,
            bid_size=20,
            ask_size=30,
            spread_pct=(ask - bid) / ((ask + bid) / 2),
            volume=12,
            open_interest=25,
            iv=0.44,
            liquidity_state=state,
            maturation_score_1d=0.35,
            maturation_score_2d=0.58,
            maturation_score_3d=0.66,
            maturation_score_is_probability=False,
            atm_distance_sigma=0.71,
            remaining_runway_pct=82.0,
        )

    def test_schema_extends_existing_registry_without_new_database(self) -> None:
        with self.registry.connection() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue(
            {
                "option_thesis_events",
                "option_contract_observations",
                "option_contract_selection_events",
            }.issubset(tables)
        )
        self.assertTrue(self.registry.validate_schema()["valid"])
        self.assertEqual(list(self.root.glob("*.sqlite")), [self.root / "control_plane.sqlite"])
        expected_lineage = {
            "calculation_version",
            "supersedes_event_id",
            "correction_reason",
            "corrected_by_run_id",
            "correction_state",
        }
        with self.registry.connection() as connection:
            for table in (
                "option_thesis_events",
                "option_contract_observations",
                "option_contract_selection_events",
            ):
                columns = {
                    row["name"]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                self.assertTrue(expected_lineage.issubset(columns), table)

    def test_corrected_thesis_supersedes_legacy_event_without_mutation(self) -> None:
        legacy = self.store.record_thesis_event(
            thesis_id="BP:PUT:2026-08-29",
            event_key="EOD:LEGACY",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.INVALIDATED,
            monitor_state=MonitorState.TERMINAL,
            reason_code="THESIS_INVALIDATED",
            invalidation_spot=39.0,
            calculation_version="options-liquidity-lifecycle-v1",
        )
        corrected = self.store.record_thesis_event(
            thesis_id="BP:PUT:2026-08-29:OLM2",
            event_key="EOD:CORRECTED",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE,
            reason_code="LIQUIDITY_PENDING",
            invalidation_spot=43.0,
            calculation_version="options-liquidity-lifecycle-v2",
            supersedes_event_id=legacy.record.event_id,
            correction_reason="LEGACY_INVALIDATION_GEOMETRY_OR_HOLD_DEFECT",
            corrected_by_run_id=RUN_ID,
            correction_state="SUPERSEDED_DATA_DEFECT",
        )

        self.assertEqual(corrected.record.supersedes_event_id, legacy.record.event_id)
        self.assertEqual(corrected.record.correction_state, "SUPERSEDED_DATA_DEFECT")
        self.assertEqual(legacy.record.thesis_state, ThesisState.INVALIDATED)
        with self.registry.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT thesis_state FROM option_thesis_events WHERE event_id = ?",
                    (legacy.record.event_id,),
                ).fetchone()[0],
                "INVALIDATED",
            )

    def test_partial_supersession_lineage_fails_closed(self) -> None:
        with self.assertRaisesRegex(DatasetValidationError, "supersession requires"):
            self.store.record_thesis_event(
                thesis_id="BP-PUT-PARTIAL",
                event_key="EOD-PARTIAL",
                run_id=RUN_ID,
                ticker="BP",
                direction="PUT",
                thesis_state=ThesisState.ACTIVE,
                monitor_state=MonitorState.ACTIVE,
                reason_code="LIQUIDITY_PENDING",
                supersedes_event_id="missing",
            )

    def test_options_persistence_links_corrected_olm2_to_legacy_terminal(self) -> None:
        legacy_id = "BP:PUT:2026-08-29"
        legacy = self.store.record_thesis_event(
            thesis_id=legacy_id,
            event_key="EOD:LEGACY-BUG",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.INVALIDATED,
            monitor_state=MonitorState.TERMINAL,
            reason_code="THESIS_INVALIDATED",
            invalidation_spot=39.0,
            calculation_version="options-liquidity-lifecycle-v1",
        )
        result = {
            "thesis_id": f"{legacy_id}:OLM2",
            "legacy_thesis_id": legacy_id,
            "ticker": "BP",
            "options_direction": "PUT",
            "thesis_state": "ACTIVE",
            "liquidity_state": "LIFECYCLE_DATA_INCOMPLETE",
            "thesis_calculation_version": "options-liquidity-lifecycle-v2",
            "quote_as_of": QUOTE_TIME.isoformat(),
        }
        with patch.object(options_intelligence, "_CDS_LIQUIDITY_STORE", self.store):
            options_intelligence._persist_options_lifecycle_result(result, RUN_ID)
            options_intelligence._persist_options_lifecycle_result(dict(result), RUN_ID)

        corrected = self.store.latest_thesis(f"{legacy_id}:OLM2")
        self.assertIsNotNone(corrected)
        self.assertEqual(corrected.supersedes_event_id, legacy.record.event_id)
        self.assertEqual(corrected.correction_state, "SUPERSEDED_DATA_DEFECT")
        self.assertEqual(corrected.calculation_version, "options-liquidity-lifecycle-v2")
        self.assertEqual(self.store.latest_thesis(legacy_id).thesis_state, ThesisState.INVALIDATED)

    def test_eod_terminal_result_persists_observation_before_closure_and_replays(self) -> None:
        result = {
            "thesis_id": "FLYW:PUT:2026-08-28",
            "ticker": "FLYW",
            "options_direction": "PUT",
            "thesis_state": "TARGET_REALIZED",
            "liquidity_state": "THESIS_TARGET_UNREACHABLE",
            "morning_transition_state": "MOVE_ALREADY_REALIZED",
            "remaining_runway_state": "MOVE_ALREADY_REALIZED",
            "executable_now": False,
            "recommended_contract": "FLYW260918P00010000",
            "option_chain_dataset_id": "chain-flyw-marketdata",
            "quote_as_of": QUOTE_TIME.isoformat(),
            "contract_quote_timestamp_utc": QUOTE_TIME.isoformat(),
            "contract_expiry": "2026-09-18",
            "contract_strike": 10.0,
            "contract_dte": 20.0,
            "underlying_price": 11.0,
            "contract_bid": 0.90,
            "contract_ask": 1.10,
            "contract_mid": 1.00,
            "contract_spread_pct": 0.20,
            "contract_delta": -0.35,
            "contract_gamma": 0.04,
            "contract_theta": -0.03,
            "contract_vega": 0.02,
            "contract_iv": 0.55,
            "contract_oi": 25,
            "contract_volume": 5,
            "contract_quote_source": "MARKETDATA",
            "contract_mark_synthetic": False,
            "structural_target": 8.0,
            "invalidation_spot": 12.0,
            "contract_selection_reason": "EOD_CONTRACT_SELECTION",
            "lifecycle_contract_version": "options-liquidity-lifecycle-v1",
        }
        with (
            patch.object(options_intelligence, "_CDS_LIQUIDITY_STORE", self.store),
            patch.object(options_intelligence, "_REPO_ROOT", self.root),
        ):
            options_intelligence._persist_options_lifecycle_result(result, RUN_ID)

            self.assertEqual(result["liquidity_persistence_status"], "PERSISTED_TERMINAL")
            self.assertEqual(
                self.store.latest_thesis(result["thesis_id"]).thesis_state,
                ThesisState.TARGET_REALIZED,
            )
            self.assertIsNotNone(self.store.latest_observation(result["thesis_id"]))
            self.assertIsNotNone(self.store.latest_selection(result["thesis_id"]))
            with self.registry.connection() as connection:
                states = [
                    row[0]
                    for row in connection.execute(
                        "SELECT thesis_state FROM option_thesis_events "
                        "WHERE thesis_id = ? ORDER BY version",
                        (result["thesis_id"],),
                    ).fetchall()
                ]
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM option_contract_observations WHERE thesis_id = ?",
                    (result["thesis_id"],),
                ).fetchone()[0]
            self.assertEqual(states, ["ACTIVE", "TARGET_REALIZED"])
            self.assertEqual(observation_count, 1)

            replayed = dict(result)
            options_intelligence._persist_options_lifecycle_result(replayed, RUN_ID)

        self.assertEqual(
            replayed["liquidity_persistence_status"],
            "TERMINAL_THESIS_ALREADY_RECORDED",
        )
        self.assertFalse(replayed["executable_now"])
        self.assertEqual(replayed["morning_transition_state"], "MOVE_ALREADY_REALIZED")
        with self.registry.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM option_thesis_events WHERE thesis_id = ?",
                    (result["thesis_id"],),
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM option_contract_observations WHERE thesis_id = ?",
                    (result["thesis_id"],),
                ).fetchone()[0],
                1,
            )

    def test_thesis_events_are_append_only_idempotent_and_versioned(self) -> None:
        first = self._thesis()
        repeated = self._thesis()
        self.assertFalse(first.reused_existing)
        self.assertTrue(repeated.reused_existing)
        self.assertEqual(first.record.version, 1)

        with self.assertRaises(OptionLifecycleConflict):
            self.store.record_thesis_event(
                thesis_id="BP-PUT-1",
                event_key="EOD-CREATED",
                run_id=RUN_ID,
                ticker="BP",
                direction="PUT",
                thesis_state=ThesisState.CONFIRMED,
                monitor_state=MonitorState.ACTIVE,
                reason_code="CHANGED_CONTENT",
            )
        with self.assertRaises(OptionLifecycleConcurrencyError):
            self.store.record_thesis_event(
                thesis_id="BP-PUT-1",
                event_key="MORNING-REFRESH",
                run_id=RUN_ID,
                ticker="BP",
                direction="PUT",
                thesis_state=ThesisState.CONFIRMED,
                monitor_state=MonitorState.ACTIVE,
                reason_code="THESIS_CONFIRMED",
            )

        second = self.store.record_thesis_event(
            thesis_id="BP-PUT-1",
            event_key="MORNING-REFRESH",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.CONFIRMED,
            monitor_state=MonitorState.ACTIVE,
            reason_code="THESIS_CONFIRMED",
            expected_version=1,
        )
        self.assertEqual(second.record.version, 2)

        # Event keys are idempotent within a thesis, not globally across tickers.
        other = self.store.record_thesis_event(
            thesis_id="XOM-CALL-1",
            event_key="EOD-CREATED",
            run_id=RUN_ID,
            ticker="XOM",
            direction="CALL",
            thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE,
            reason_code="LIQUIDITY_PENDING",
        )
        self.assertEqual(other.record.version, 1)

        with self.registry.connection() as connection:
            with self.assertRaisesRegex(Exception, "append-only"):
                connection.execute(
                    "UPDATE option_thesis_events SET reason_code='MUTATED' "
                    "WHERE thesis_id='BP-PUT-1'"
                )

    def test_observations_require_marketdata_canonical_provenance(self) -> None:
        self._thesis()
        marketdata_id = self._dataset()
        polygon_id = self._dataset(provider="POLYGON")

        with self.assertRaisesRegex(DatasetValidationError, "must be MARKETDATA"):
            self.store.record_contract_observation(
                thesis_id="BP-PUT-1",
                run_id=RUN_ID,
                ticker="BP",
                contract_symbol="BP260918P00040000",
                option_side="PUT",
                quote_as_of=QUOTE_TIME,
                source_dataset_id=marketdata_id,
                source_provider="POLYGON",
                spot=41,
                strike=40,
                expiration=date(2026, 9, 18),
                dte=20,
                liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
            )
        with self.assertRaisesRegex(DatasetValidationError, "not MARKETDATA"):
            self.store.record_contract_observation(
                thesis_id="BP-PUT-1",
                run_id=RUN_ID,
                ticker="BP",
                contract_symbol="BP260918P00040000",
                option_side="PUT",
                quote_as_of=QUOTE_TIME,
                source_dataset_id=polygon_id,
                spot=41,
                strike=40,
                expiration=date(2026, 9, 18),
                dte=20,
                liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
            )

    def test_observation_identity_is_idempotent_and_conflicts_fail_closed(self) -> None:
        self._thesis()
        dataset_id = self._dataset()
        first = self._observation(dataset_id=dataset_id)
        repeated = self._observation(dataset_id=dataset_id)
        self.assertFalse(first.reused_existing)
        self.assertTrue(repeated.reused_existing)
        self.assertEqual(first.record.observation_id, repeated.record.observation_id)
        self.assertFalse(first.record.maturation_score_is_probability)
        self.assertEqual(first.record.maturation_score_2d, 0.58)
        self.assertIsNone(first.record.maturation_probability_2d)
        with self.assertRaises(OptionLifecycleConflict):
            self._observation(dataset_id=dataset_id, bid=0.8)

        with self.assertRaisesRegex(DatasetValidationError, "reserved"):
            self.store.record_contract_observation(
                thesis_id="BP-PUT-1",
                run_id=RUN_ID,
                ticker="BP",
                contract_symbol="BP260918P00039000",
                option_side="PUT",
                quote_as_of=QUOTE_TIME + timedelta(minutes=2),
                source_dataset_id=dataset_id,
                spot=41,
                strike=39,
                expiration=date(2026, 9, 18),
                dte=20,
                liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
                maturation_probability_2d=0.60,
            )

    def test_same_provider_quote_reuses_observation_across_canonical_wrappers(self) -> None:
        self._thesis()
        chain_id = self._dataset()
        exact_id = self._dataset(
            dataset_type=DatasetType.EXACT_OPTION_QUOTE,
            suffix="-exact",
        )
        first = self._observation(dataset_id=chain_id)
        replay = self.store.record_contract_observation(
            thesis_id="BP-PUT-1",
            run_id=RUN_ID,
            ticker="BP",
            contract_symbol="BP260918P00040000",
            option_side="PUT",
            quote_as_of=QUOTE_TIME,
            source_dataset_id=exact_id,
            spot=41.25,
            strike=40.0,
            expiration=date(2026, 9, 18),
            dte=19,
            delta=-0.32,
            bid=0.9,
            ask=1.2,
            bid_size=20,
            ask_size=30,
            spread_pct=(1.2 - 0.9) / ((1.2 + 0.9) / 2),
            volume=12,
            open_interest=25,
            iv=0.44,
            liquidity_state=ContractLiquidityState.EXECUTABLE_NOW,
            maturation_score_1d=62.0,
            maturation_score_2d=71.0,
            maturation_score_3d=78.0,
            maturation_score_is_probability=False,
            atm_distance_sigma=0.60,
            remaining_runway_pct=75.0,
            calculation_version="options-liquidity-morning-v2",
        )
        self.assertTrue(replay.reused_existing)
        self.assertEqual(replay.record.observation_id, first.record.observation_id)
        self.assertEqual(replay.record.source_dataset_id, chain_id)

    def test_same_timestamp_with_changed_quote_content_still_fails_closed(self) -> None:
        self._thesis()
        chain_id = self._dataset()
        exact_id = self._dataset(
            dataset_type=DatasetType.EXACT_OPTION_QUOTE,
            suffix="-changed",
        )
        self._observation(dataset_id=chain_id)
        with self.assertRaises(OptionLifecycleConflict):
            self.store.record_contract_observation(
                thesis_id="BP-PUT-1",
                run_id=RUN_ID,
                ticker="BP",
                contract_symbol="BP260918P00040000",
                option_side="PUT",
                quote_as_of=QUOTE_TIME,
                source_dataset_id=exact_id,
                spot=41.25,
                strike=40.0,
                expiration=date(2026, 9, 18),
                dte=20,
                delta=-0.32,
                bid=0.95,
                ask=1.2,
                bid_size=20,
                ask_size=30,
                spread_pct=(1.2 - 0.95) / ((1.2 + 0.95) / 2),
                volume=12,
                open_interest=25,
                iv=0.44,
                liquidity_state=ContractLiquidityState.EXECUTABLE_NOW,
            )

    def test_active_monitor_reuses_fresh_data_and_fetches_only_missing_or_stale(self) -> None:
        self._thesis()
        missing = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=300, now=QUOTE_TIME
        )
        self.assertTrue(missing.should_fetch)
        self.assertEqual(missing.provider, "MARKETDATA")
        self.assertEqual(missing.reason, "OBSERVATION_MISSING")

        dataset_id = self._dataset()
        self._observation(dataset_id=dataset_id)
        fresh = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=300, now=QUOTE_TIME + timedelta(seconds=60)
        )
        self.assertFalse(fresh.should_fetch)
        self.assertEqual(fresh.reason, "FRESH_CANONICAL_OBSERVATION")
        stale = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=300, now=QUOTE_TIME + timedelta(hours=2)
        )
        self.assertTrue(stale.should_fetch)
        self.assertEqual(stale.provider, "MARKETDATA")
        self.assertEqual(stale.reason, "CANONICAL_OBSERVATION_STALE")

        worklist = self.store.active_monitor_worklist(
            freshness_seconds=300, now=QUOTE_TIME + timedelta(hours=2)
        )
        self.assertEqual([item.thesis.ticker for item in worklist], ["BP"])
        self.assertTrue(worklist[0].fetch_decision.should_fetch)

    def test_terminal_drop_stops_monitoring_and_future_fetch(self) -> None:
        self._thesis()
        terminal = self.store.record_thesis_event(
            thesis_id="BP-PUT-1",
            event_key="THESIS-INVALIDATED",
            run_id=RUN_ID,
            ticker="BP",
            direction="PUT",
            thesis_state=ThesisState.INVALIDATED,
            monitor_state=MonitorState.TERMINAL,
            reason_code="INVALIDATION_CROSSED",
            expected_version=1,
        )
        self.assertEqual(terminal.record.version, 2)
        decision = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=0, now=QUOTE_TIME
        )
        self.assertFalse(decision.should_fetch)
        self.assertEqual(decision.provider, None)
        self.assertEqual(decision.reason, "THESIS_INVALIDATED")
        self.assertEqual(
            self.store.active_monitor_worklist(
                freshness_seconds=0, now=QUOTE_TIME
            ),
            (),
        )
        with self.assertRaisesRegex(DatasetValidationError, "terminal thesis"):
            self._observation(dataset_id=self._dataset())

    def test_executable_quote_leaves_pending_worklist_but_is_refetched_when_stale(self) -> None:
        self._thesis()
        self._observation(
            dataset_id=self._dataset(),
            state=ContractLiquidityState.EXECUTABLE_NOW,
        )
        fresh = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=300, now=QUOTE_TIME + timedelta(seconds=30)
        )
        self.assertFalse(fresh.should_fetch)
        self.assertEqual(fresh.reason, "FRESH_EXECUTABLE_CONTRACT")
        self.assertEqual(
            self.store.active_monitor_worklist(
                freshness_seconds=300, now=QUOTE_TIME + timedelta(seconds=30)
            ),
            (),
        )
        stale = self.store.should_fetch(
            "BP-PUT-1", freshness_seconds=300, now=QUOTE_TIME + timedelta(hours=1)
        )
        self.assertTrue(stale.should_fetch)
        self.assertEqual(stale.reason, "CANONICAL_OBSERVATION_STALE")
        self.assertEqual(
            len(
                self.store.active_monitor_worklist(
                    freshness_seconds=300, now=QUOTE_TIME + timedelta(hours=1)
                )
            ),
            1,
        )

    def test_selection_change_requires_exact_economics_recomputation(self) -> None:
        self._thesis()
        dataset_id = self._dataset()
        first_observation = self._observation(dataset_id=dataset_id).record
        first = self.store.record_selection_event(
            thesis_id="BP-PUT-1",
            event_key="EOD-SELECTION",
            run_id=RUN_ID,
            selected_contract_symbol=first_observation.contract_symbol,
            selected_observation_id=first_observation.observation_id,
            selection_reason="BEST_CURRENT_CONTRACT",
            economics_recomputed=True,
        )
        repeated = self.store.record_selection_event(
            thesis_id="BP-PUT-1",
            event_key="EOD-SELECTION",
            run_id=RUN_ID,
            selected_contract_symbol=first_observation.contract_symbol,
            selected_observation_id=first_observation.observation_id,
            selection_reason="BEST_CURRENT_CONTRACT",
            economics_recomputed=True,
        )
        self.assertTrue(repeated.reused_existing)
        self.assertEqual(first.record.selection_version, 1)

        replacement = self._observation(
            dataset_id=dataset_id,
            contract="BP260918P00041000",
            quote_as_of=QUOTE_TIME + timedelta(minutes=1),
        ).record
        with self.assertRaisesRegex(DatasetValidationError, "recomputation"):
            self.store.record_selection_event(
                thesis_id="BP-PUT-1",
                event_key="MORNING-REPAIR",
                run_id=RUN_ID,
                previous_contract_symbol=first_observation.contract_symbol,
                selected_contract_symbol=replacement.contract_symbol,
                selected_observation_id=replacement.observation_id,
                selection_reason="BETTER_LIQUIDITY",
                economics_recomputed=False,
                expected_version=1,
            )
        repaired = self.store.record_selection_event(
            thesis_id="BP-PUT-1",
            event_key="MORNING-REPAIR",
            run_id=RUN_ID,
            previous_contract_symbol=first_observation.contract_symbol,
            selected_contract_symbol=replacement.contract_symbol,
            selected_observation_id=replacement.observation_id,
            selection_reason="BETTER_LIQUIDITY",
            economics_recomputed=True,
            expected_version=1,
        )
        self.assertEqual(repaired.record.selection_version, 2)
        self.assertTrue(repaired.record.economics_recomputed)

    def test_morning_marketdata_quotes_append_without_a_second_database(self) -> None:
        result = {
            "ticker": "BP",
            "direction": "PUT",
            "final_direction": "PUT",
            "thesis_id": "BP-PUT-MORNING-1",
            "morning_transition_state": "EXECUTABLE_NOW",
            "liquidity_state": "EXECUTABLE_NOW",
            "morning_selected_contract_symbol": "O:BP260918P00040000",
            "contract_symbol": "O:BP260918P00040000",
            "live_options_source": "MARKETDATA",
            "live_options_fetched_at": "2026-08-29T08:00:01Z",
            "live_contract_provider_updated": "2026-08-29T08:00:00Z",
            "live_price": 41.0,
            "live_contract_bid": 0.90,
            "live_contract_ask": 1.00,
            "live_contract_mid": 0.95,
            "live_contract_spread_pct": 10.5263,
            "live_contract_delta": -0.32,
            "live_contract_gamma": 0.03,
            "live_contract_theta": -0.02,
            "live_contract_vega": 0.08,
            "live_contract_iv": 0.44,
            "live_contract_oi": 12,
            "live_contract_volume": 3,
            "maturation_score_1d": 62.0,
            "maturation_score_2d": 71.0,
            "maturation_score_3d": 78.0,
            "maturation_score_is_probability": False,
            "atm_distance_sigma": 0.71,
            "remaining_runway_pct": 82.0,
            "selected_contract_economics_ready": True,
            "contract_changed": False,
        }
        with patch.object(morning_gate, "ROOT", self.root):
            morning_gate._persist_morning_liquidity_result(
                result, RUN_ID, self.registry, self.store
            )
            self.assertEqual(result["morning_liquidity_persistence_status"], "PERSISTED")

            # A changed quote in a second gate pass is a new immutable event,
            # not an overwrite and not a conflict on the shared run_id.
            refreshed = dict(result)
            refreshed.update({
                "live_options_fetched_at": "2026-08-29T08:05:01Z",
                "live_contract_provider_updated": "2026-08-29T08:05:00Z",
                "live_contract_bid": 1.00,
                "live_contract_ask": 1.10,
                "live_contract_mid": 1.05,
            })
            morning_gate._persist_morning_liquidity_result(
                refreshed, RUN_ID, self.registry, self.store
            )
            replayed = dict(refreshed)
            morning_gate._persist_morning_liquidity_result(
                replayed, RUN_ID, self.registry, self.store
            )

        self.assertEqual(refreshed["morning_liquidity_persistence_status"], "PERSISTED")
        self.assertEqual(replayed["morning_liquidity_persistence_status"], "PERSISTED")
        self.assertTrue(replayed["selected_quote_dataset_id"])
        self.assertEqual(self.store.latest_thesis("BP-PUT-MORNING-1").version, 2)
        self.assertEqual(self.store.latest_selection("BP-PUT-MORNING-1").selection_version, 2)
        self.assertEqual(
            self.store.latest_observation("BP-PUT-MORNING-1").maturation_score_2d,
            71.0,
        )
        self.assertEqual(list(self.root.glob("*.sqlite")), [self.root / "control_plane.sqlite"])

        with (
            patch.object(morning_gate, "_fetch_live_price", return_value={"live_price": 41.0}),
            patch.object(morning_gate, "_fetch_options_skew", return_value={}),
            patch.object(
                morning_gate,
                "_fetch_live_contract",
                side_effect=AssertionError("fresh CDS quote must suppress MarketData refetch"),
            ),
        ):
            live = morning_gate._fetch_all_live(
                [{
                    "ticker": "BP",
                    "thesis_id": "BP-PUT-MORNING-1",
                    "direction": "PUT",
                    "canonical_direction": "PUT",
                    "options_strategy": "LONG_PUT",
                    "contract_symbol": "O:BP260918P00040000",
                }],
                spread_threshold=25.0,
                liquidity_store=self.store,
                liquidity_freshness_seconds=10**9,
            )["BP"]
        self.assertEqual(live["live_options_resolution"], "CDS_FRESH_QUOTE_HIT")

    def test_morning_persistence_reuses_msi_exact_quote_dataset(self) -> None:
        exact_id = self._dataset(
            dataset_type=DatasetType.EXACT_OPTION_QUOTE,
            suffix="-morning-exact",
        )
        result = {
            "ticker": "BP",
            "direction": "PUT",
            "final_direction": "PUT",
            "thesis_id": "BP-PUT-MSI-1",
            "morning_transition_state": "EXECUTABLE_NOW",
            "liquidity_state": "EXECUTABLE_NOW",
            "morning_selected_contract_symbol": "O:BP260918P00040000",
            "contract_symbol": "O:BP260918P00040000",
            "live_options_source": "MARKETDATA",
            "live_options_fetched_at": "2026-08-29T08:00:01Z",
            "live_contract_provider_updated": "2026-08-29T08:00:00Z",
            "live_price": 41.0,
            "live_contract_bid": 0.90,
            "live_contract_ask": 1.00,
            "live_contract_spread_pct": 10.5263,
            "live_contract_delta": -0.32,
            "live_contract_iv": 0.44,
            "live_contract_oi": 12,
            "live_contract_volume": 3,
            "maturation_score_1d": 62.0,
            "maturation_score_2d": 71.0,
            "maturation_score_3d": 78.0,
            "atm_distance_sigma": 0.71,
            "remaining_runway_pct": 82.0,
            "selected_contract_economics_ready": True,
            "contract_changed": False,
            "msi_exact_quote_dataset_id": exact_id,
        }
        with patch.object(morning_gate, "ROOT", self.root):
            morning_gate._persist_morning_liquidity_result(
                result, RUN_ID, self.registry, self.store
            )

        self.assertEqual(result["morning_liquidity_persistence_status"], "PERSISTED")
        self.assertEqual(result["selected_quote_dataset_id"], exact_id)
        latest = self.store.latest_observation("BP-PUT-MSI-1")
        self.assertEqual(latest.source_dataset_id, exact_id)
        with self.registry.connection() as connection:
            live_wrappers = connection.execute(
                "SELECT COUNT(*) FROM dataset_registry WHERE dataset_type = ?",
                (DatasetType.LIVE_OPTION.value,),
            ).fetchone()[0]
        self.assertEqual(live_wrappers, 0)


if __name__ == "__main__":
    unittest.main()
