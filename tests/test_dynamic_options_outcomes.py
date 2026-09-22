from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.dynamic_options_outcomes import DynamicOptionsOutcomeCaptureService
from canonical_data.option_outcome_maturation import (
    read_exact_contract_option_path, read_completed_underlying_path,
    capture_matured_family, capture_matured_option_batch,
)
from canonical_data.phantom_outcome_source import VerifiedPhantomOutcomeQuote
from canonical_data.historical_prices import HistoricalPriceDatabase
from canonical_data.outcome_learning import load_option_outcome_lookup
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState, MonitorState, OptionLifecycleConflict,
    OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ContractAssessment, ContractEntryState, ContractFamily,
    ModelApplicabilityState, UnderlyingThesisRef,
)
from domain.dynamic_options_outcomes import (
    DOIOutcomeLabel, OptionPathObservation, OutcomeDataStatus,
    OutcomeLeakageError, UnderlyingPathObservation,
    chronological_outcome_cohorts, evaluate_assessment_outcome,
    outcome_label_identity,
)


UTC = timezone.utc
RUN_ID = "20260910_220000"
ORIGIN = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
EVALUATION = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
CALL_SYMBOL = "ABC261016C00100000"
PUT_SYMBOL = "ABC261016P00100000"


def _underlying(count: int = 5, *, direction: str = "CALL") -> tuple[UnderlyingPathObservation, ...]:
    items = []
    for index in range(1, count + 1):
        session = date(2026, 9, 1) + timedelta(days=index)
        base = 100 + index if direction == "CALL" else 100 - index
        items.append(UnderlyingPathObservation(
            dataset_id=f"UNDERLYING-{direction}-{index}", session_date=session,
            available_at_utc=datetime.combine(session, datetime.min.time(), UTC) + timedelta(hours=22),
            high=base + 2, low=base - 2, close=base,
        ))
    return tuple(items)


def _options(
    count: int = 5, *, symbol: str = CALL_SYMBOL, start_bid: float = 1.8,
) -> tuple[OptionPathObservation, ...]:
    items = []
    for index in range(1, count + 1):
        session = date(2026, 9, 1) + timedelta(days=index)
        bid = start_bid + index * 0.2
        ask = bid + (0.8 if index == 1 else 0.2)
        quote = datetime.combine(session, datetime.min.time(), UTC) + timedelta(hours=20)
        items.append(OptionPathObservation(
            observation_id=f"OBS-{symbol}-{index}", dataset_id=f"OPTION-{symbol}-{index}",
            contract_symbol=symbol, session_date=session, quote_at_utc=quote,
            available_at_utc=quote + timedelta(minutes=1), bid=bid, ask=ask,
            volume=10 * index, open_interest=20 * index, implied_volatility=0.35,
        ))
    return tuple(items)


def _label(
    *, direction: str = "CALL", horizon: int = 5,
    option_path=None, underlying_path=None, reference_bid=1.8, reference_ask=2.0,
) -> DOIOutcomeLabel:
    symbol = CALL_SYMBOL if direction == "CALL" else PUT_SYMBOL
    return evaluate_assessment_outcome(
        assessment_id=f"ASSESS-{direction}", family_id=f"FAMILY-{direction}",
        thesis_id=f"THESIS-{direction}", run_id=RUN_ID, ticker="ABC",
        contract_symbol=symbol, original_observation_id=f"ORIGIN-{direction}",
        direction=direction, assessment_cutoff_utc=ORIGIN,
        evaluation_cutoff_utc=EVALUATION, horizon_sessions=horizon,
        reference_spot=100, reference_bid=reference_bid, reference_ask=reference_ask,
        target_spot=105 if direction == "CALL" else 95,
        invalidation_spot=95 if direction == "CALL" else 105,
        option_path=_options(symbol=symbol) if option_path is None else option_path,
        underlying_path=_underlying(direction=direction) if underlying_path is None else underlying_path,
    )


class DynamicOutcomeDomainTests(unittest.TestCase):
    def test_late_backfilled_quote_advances_label_evidence_cutoff(self) -> None:
        delayed = replace(
            _options(count=1)[0],
            available_at_utc=datetime(2026, 9, 9, 21, tzinfo=UTC),
        )
        label = _label(
            horizon=1, option_path=(delayed,),
            underlying_path=_underlying(count=1),
        )
        self.assertEqual(label.outcome_cutoff_utc,
                         datetime(2026, 9, 9, 21, tzinfo=UTC))

    def test_complete_call_label_calculates_paths_and_liquidity(self) -> None:
        result = _label()
        self.assertIs(result.data_status, OutcomeDataStatus.COMPLETE)
        self.assertEqual(result.option_points_observed, 5)
        self.assertEqual(result.underlying_points_observed, 5)
        self.assertGreater(result.option_executable_mfe, result.option_executable_mae)
        self.assertGreater(result.underlying_mfe, 0)
        self.assertLessEqual(result.underlying_mae, 0)
        self.assertEqual(result.first_two_sided_session, 1)
        self.assertIsNotNone(result.first_spread_15_session)
        self.assertEqual(result.target_first_hit_session, 3)
        self.assertEqual(result.decision_authority, "NONE")
        self.assertFalse(result.can_grant_capital)

    def test_put_path_is_directionally_symmetric(self) -> None:
        call = _label(direction="CALL")
        put = _label(direction="PUT", option_path=_options(symbol=PUT_SYMBOL))
        self.assertAlmostEqual(call.underlying_directional_return, put.underlying_directional_return)
        self.assertAlmostEqual(call.underlying_mfe, put.underlying_mfe)
        self.assertEqual(call.target_first_hit_session, put.target_first_hit_session)

    def test_incomplete_horizon_is_deferred_not_zero_filled(self) -> None:
        result = _label(horizon=5, underlying_path=_underlying(2), option_path=_options(2))
        self.assertIs(result.data_status, OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE)
        self.assertIsNone(result.underlying_directional_return)
        self.assertIn("UNDERLYING_HORIZON_NOT_MATURE", result.data_gap_reasons)

    def test_mature_underlying_with_no_option_path_is_retained_as_partial(self) -> None:
        result = _label(option_path=())
        self.assertIs(result.data_status, OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL)
        self.assertIsNotNone(result.underlying_directional_return)
        self.assertIsNone(result.option_executable_mfe)
        self.assertIn("NO_FUTURE_EXACT_CONTRACT_OBSERVATIONS", result.data_gap_reasons)

    def test_missing_reference_quote_does_not_invent_option_return(self) -> None:
        result = _label(reference_bid=None, reference_ask=None)
        self.assertIs(result.data_status, OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE)
        self.assertIsNone(result.terminal_option_mid_return)
        self.assertIsNone(result.terminal_executable_return)

    def test_exact_contract_identity_cannot_change(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact contract"):
            _label(option_path=_options(symbol=PUT_SYMBOL))

    def test_assessment_session_and_future_cutoff_leakage_fail_closed(self) -> None:
        current = replace(
            _options(1)[0], session_date=ORIGIN.date(),
            quote_at_utc=ORIGIN, available_at_utc=ORIGIN,
        )
        with self.assertRaises(OutcomeLeakageError):
            _label(option_path=(current,))
        future = replace(_options(1)[0], available_at_utc=EVALUATION + timedelta(seconds=1))
        with self.assertRaises(OutcomeLeakageError):
            _label(option_path=(future,))

    def test_after_midnight_assessment_uses_source_market_session(self) -> None:
        # EOD publication after 00:00 UTC belongs to the prior US session.
        assessment_cutoff = datetime(2026, 9, 2, 0, 30, tzinfo=UTC)
        future_session = date(2026, 9, 2)
        quote = datetime(2026, 9, 2, 20, tzinfo=UTC)
        option = OptionPathObservation(
            observation_id="NEXT-SESSION", dataset_id="NEXT-DATASET",
            contract_symbol=CALL_SYMBOL, session_date=future_session,
            quote_at_utc=quote, available_at_utc=quote + timedelta(minutes=1),
            bid=2.3, ask=2.5,
        )
        underlying = UnderlyingPathObservation(
            dataset_id="NEXT-PRICE", session_date=future_session,
            available_at_utc=quote + timedelta(hours=1),
            high=106, low=99, close=105,
        )
        label = evaluate_assessment_outcome(
            assessment_id="AFTER-MIDNIGHT", family_id="FAMILY-CALL",
            thesis_id="THESIS-CALL", run_id=RUN_ID, ticker="ABC",
            contract_symbol=CALL_SYMBOL, original_observation_id="ORIGIN-CALL",
            direction="CALL", assessment_cutoff_utc=assessment_cutoff,
            assessment_session_date=date(2026, 9, 1),
            evaluation_cutoff_utc=EVALUATION, horizon_sessions=1,
            reference_spot=100, reference_bid=1.8, reference_ask=2.0,
            target_spot=105, invalidation_spot=95,
            option_path=(option,), underlying_path=(underlying,),
        )
        self.assertEqual(label.option_points_observed, 1)
        self.assertEqual(label.underlying_points_observed, 1)

    def test_latest_same_session_quote_is_used_once(self) -> None:
        first = _options(1)[0]
        later = replace(
            first, observation_id="OBS-LATER", quote_at_utc=first.quote_at_utc + timedelta(minutes=5),
            available_at_utc=first.available_at_utc + timedelta(minutes=5), bid=3.0, ask=3.2,
        )
        result = _label(horizon=1, option_path=(first, later), underlying_path=_underlying(1))
        self.assertEqual(result.option_points_observed, 1)
        self.assertEqual(result.source_option_observation_ids, ("OBS-LATER",))

    def test_same_session_target_and_invalidation_are_not_ordered(self) -> None:
        bar = UnderlyingPathObservation(
            "U-BOTH", date(2026, 9, 2), datetime(2026, 9, 2, 22, tzinfo=UTC),
            high=106, low=94, close=100,
        )
        result = _label(horizon=1, underlying_path=(bar,), option_path=_options(1))
        self.assertEqual(result.first_passage_state, "AMBIGUOUS_SAME_SESSION")

    def test_realisations_cannot_be_laundered_into_hypothetical_label(self) -> None:
        with self.assertRaisesRegex(ValueError, "hypothetical"):
            replace(_label(), uses_realised_fills=True)

    def test_chronological_cohorts_exclude_boundary_overlap(self) -> None:
        training = _label(horizon=1, option_path=_options(1), underlying_path=_underlying(1))
        overlapping = _label(horizon=5)
        validation = replace(
            training, label_id="VALIDATION", assessment_id="ASSESS-VAL",
            assessment_cutoff_utc=datetime(2026, 9, 4, 20, tzinfo=UTC),
            outcome_cutoff_utc=datetime(2026, 9, 5, 22, tzinfo=UTC),
        )
        cohorts = chronological_outcome_cohorts(
            (training, overlapping, validation),
            training_cutoff_utc=datetime(2026, 9, 3, 23, tzinfo=UTC),
            validation_cutoff_utc=datetime(2026, 9, 6, 23, tzinfo=UTC),
        )
        self.assertEqual(cohorts.training, (training,))
        self.assertEqual(cohorts.validation, (validation,))
        self.assertEqual(cohorts.excluded_boundary_overlap, (overlapping,))


class DynamicOutcomePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.registry = CanonicalRegistry(self.root / "control.sqlite")
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", ORIGIN.date())
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()
        self.thesis = UnderlyingThesisRef(
            thesis_id="THESIS-CALL", thesis_version=1, ticker="ABC",
            governed_direction="CALL", origin_spot=100,
            origin_timestamp_utc=ORIGIN - timedelta(minutes=1),
            target_spot=105, invalidation_spot=95, planned_hold_sessions=5,
            planned_hold_source="HORIZON_ROUTER", evidence_cutoff_utc=ORIGIN,
        )
        self.store.record_thesis_event(
            thesis_id=self.thesis.thesis_id, event_key="ORIGIN", run_id=RUN_ID,
            ticker="ABC", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="GOVERNED_THESIS",
            structural_target=105, invalidation_spot=95,
            horizon_end_date=date(2026, 10, 1), recorded_at=ORIGIN,
        )
        self.origin_dataset = self._dataset("ORIGIN-DATASET", ORIGIN.date(), ORIGIN)
        origin = self.store.record_contract_observation(
            thesis_id=self.thesis.thesis_id, run_id=RUN_ID, ticker="ABC",
            contract_symbol=CALL_SYMBOL, option_side="CALL", quote_as_of=ORIGIN,
            source_dataset_id=self.origin_dataset, spot=100, strike=100,
            expiration=date(2026, 10, 16), dte=45,
            liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
            observed_at=ORIGIN, bid=1.8, ask=2.0, volume=10, open_interest=20,
        ).record
        self.family = ContractFamily.create(
            thesis=self.thesis, run_id=RUN_ID, family_policy_version="FAMILY-V1",
            evidence_cutoff_utc=ORIGIN, candidate_symbols=(CALL_SYMBOL,),
            source_dataset_ids=(self.origin_dataset,),
            family_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            created_at=ORIGIN,
        )
        self.family = self.store.record_contract_family(self.family).record
        self.assessment = ContractAssessment.create(
            family_id=self.family.family_id, thesis_id=self.thesis.thesis_id,
            run_id=RUN_ID, contract_symbol=CALL_SYMBOL,
            observation_id=origin.observation_id,
            entry_state=ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
            applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            evidence_cutoff_utc=ORIGIN, input_dataset_ids=(self.origin_dataset,),
            calculation_version="ASSESS-V1", feature_version="FEATURE-V1",
            model_version="NOT_EVALUATED", ranking_score_uncalibrated=0.5,
        )
        self.assessment = self.store.record_contract_assessment(self.assessment).record
        self.future_options = self._persist_future_options()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _dataset(self, token: str, session: date, observed: datetime) -> str:
        dataset_id = hashlib.sha256(token.encode()).hexdigest()
        path = self.root / f"{dataset_id}.json"
        path.write_text(json.dumps({"token": token}), encoding="utf-8")
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id="ABC", session_date=session,
            scope=DataScope(start_date=session, end_date=session, sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=dataset_id,
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=observed, as_of=observed,
            adjustment_convention="RAW_OPTION_CONTRACT", schema_version="option_chain_v2",
            source_run_id=RUN_ID,
        ))
        return dataset_id

    def _persist_future_options(self):
        points = []
        for index, point in enumerate(_options(), 1):
            dataset_id = self._dataset(f"FUTURE-{index}", point.session_date, point.available_at_utc)
            record = self.store.record_contract_observation(
                thesis_id=self.thesis.thesis_id, run_id=RUN_ID, ticker="ABC",
                contract_symbol=CALL_SYMBOL, option_side="CALL",
                quote_as_of=point.quote_at_utc, observed_at=point.available_at_utc,
                source_dataset_id=dataset_id, spot=100 + index, strike=100,
                expiration=date(2026, 10, 16), dte=45 - index,
                liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
                bid=point.bid, ask=point.ask, volume=point.volume,
                open_interest=point.open_interest,
            ).record
            points.append(OptionPathObservation(
                observation_id=record.observation_id, dataset_id=dataset_id,
                contract_symbol=record.contract_symbol,
                session_date=record.quote_as_of.date(), quote_at_utc=record.quote_as_of,
                available_at_utc=record.observed_at, bid=record.bid, ask=record.ask,
                volume=record.volume, open_interest=record.open_interest,
            ))
        return tuple(points)

    def _service(self, **overrides):
        option_reader = overrides.get("read_option_path", lambda _: self.future_options)
        underlying_reader = overrides.get("read_underlying_path", lambda _: _underlying())
        return DynamicOptionsOutcomeCaptureService(self.store).capture_family(
            family_id=self.family.family_id, evaluation_cutoff_utc=EVALUATION,
            read_option_path=option_reader, read_underlying_path=underlying_reader,
            horizons=overrides.get("horizons", (1, 5)),
        )

    def test_service_reconciles_every_assessment_and_never_calls_provider(self) -> None:
        result = self._service()
        self.assertEqual(result.summary.expected_labels, 2)
        self.assertEqual(result.summary.labels_built, 2)
        self.assertTrue(result.summary.reconciled)
        self.assertEqual(result.summary.provider_calls, 0)
        self.assertEqual(result.summary.call_assessments, 1)
        self.assertTrue(all(label.is_counterfactual for label in result.labels))

    def test_persistence_is_idempotent_append_only_and_round_trips(self) -> None:
        first = self._service(horizons=(1,))
        second = self._service(horizons=(1,))
        label = first.labels[0]
        self.assertEqual(second.summary.labels_reused, 1)
        loaded = self.store.doi_outcome_label(label.label_id)
        self.assertEqual(loaded.to_dict(), label.to_dict())
        self.assertEqual(len(self.store.outcome_labels_for_assessment(self.assessment.assessment_id)), 1)
        self.assertEqual(
            self.store.doi_outcome_labels(
                data_statuses=(OutcomeDataStatus.COMPLETE,), horizon_sessions=1
            ),
            (label,),
        )
        with self.registry.connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE doi_outcome_labels SET ticker='ZZZ'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM doi_outcome_labels")

    def test_verified_phantom_source_projects_only_into_outcome_evidence(self) -> None:
        source = self.future_options[0]
        row_hash = "b" * 64
        source_key = hashlib.sha256(
            f"{source.dataset_id}|{CALL_SYMBOL}|{row_hash}".encode()
        ).hexdigest()
        verified = VerifiedPhantomOutcomeQuote(
            observation=replace(source, observation_id="PHANTOM_REV:" + source_key),
            event_id="PHANTOM-EVENT-1", row_content_hash=row_hash,
            dataset_content_hash=source.dataset_id,
            projected_at_utc=source.available_at_utc,
        )
        self.store.ensure_outcome_source_schema()
        self.assertFalse(self.store.record_outcome_source_quote(verified).reused_existing)
        self.assertTrue(self.store.record_outcome_source_quote(verified).reused_existing)
        label = self._service(
            horizons=(1,), read_option_path=lambda _: (verified.observation,),
        ).labels[0]
        self.assertEqual(label.source_option_observation_ids,
                         (verified.observation.observation_id,))
        with self.registry.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM doi_outcome_source_quotes"
            ).fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM doi_outcome_source_quotes")
        self.assertEqual(self.store.contract_observation(
            verified.observation.observation_id), None)

    def test_matured_capture_supplements_only_missing_sessions(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ], provider="MARKETDATA", source_kind="TEST")
        source = self.future_options[4]
        row_hash = "c" * 64
        source_key = hashlib.sha256(
            f"{source.dataset_id}|{CALL_SYMBOL}|{row_hash}".encode()
        ).hexdigest()
        verified = VerifiedPhantomOutcomeQuote(
            observation=replace(source, observation_id="PHANTOM_REV:" + source_key),
            event_id="PHANTOM-EVENT-5", row_content_hash=row_hash,
            dataset_content_hash=source.dataset_id,
            projected_at_utc=source.available_at_utc,
        )

        class Reader:
            seen = None

            def read_sessions(self, **kwargs):
                self.seen = kwargs["sessions"]
                return (verified,)

        reader = Reader()
        with patch(
            "canonical_data.option_outcome_maturation.read_exact_contract_option_path",
            return_value=self.future_options[:4],
        ):
            partial = capture_matured_family(
                self.store, prices, family_id=self.family.family_id,
                evaluation_cutoff_utc=datetime.now(UTC) + timedelta(minutes=1),
                horizons=(5,),
            ).labels[0]
            result = capture_matured_family(
                self.store, prices, family_id=self.family.family_id,
                evaluation_cutoff_utc=datetime.now(UTC) + timedelta(minutes=1),
                horizons=(5,),
                phantom_source_reader=reader,
            )
        self.assertIs(partial.data_status,
                      OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL)
        self.assertEqual(reader.seen, (source.session_date,))
        self.assertIs(result.labels[0].data_status, OutcomeDataStatus.COMPLETE)
        self.assertEqual(result.labels[0].supersedes_label_id, partial.label_id)
        self.assertEqual(len(self.store.outcome_labels_for_assessment(
            self.assessment.assessment_id)), 2)
        self.assertIn(verified.observation.observation_id,
                      result.labels[0].source_option_observation_ids)

    def test_same_identity_with_different_content_fails_closed(self) -> None:
        label = self._service(horizons=(1,)).labels[0]
        forged = replace(label, maximum_volume=999)
        with self.assertRaises(OptionLifecycleConflict):
            self.store.record_doi_outcome_label(forged)

    def test_reader_failure_is_recorded_per_horizon_not_family_abort(self) -> None:
        def fail(_):
            raise RuntimeError("frozen path missing")
        result = self._service(read_option_path=fail, horizons=(1, 5))
        self.assertEqual(result.summary.labels_built, 2)
        self.assertEqual(result.summary.data_exceptions, 2)
        self.assertTrue(result.summary.reconciled)
        self.assertTrue(all(item.data_status is OutcomeDataStatus.DATA_EXCEPTION for item in result.labels))

    def test_schema_marker_and_authority_constraints_exist(self) -> None:
        with self.registry.connection() as connection:
            versions = {row[0] for row in connection.execute("SELECT schema_version FROM schema_metadata")}
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='doi_outcome_labels'"
            ).fetchone()[0]
        self.assertIn("doi_outcome_labels_v1", versions)
        self.assertIn("uses_realised_fills = 0", sql)
        self.assertIn("decision_authority = 'NONE'", sql)

    def test_canonical_reader_uses_exact_symbol_and_dataset_session(self) -> None:
        path = read_exact_contract_option_path(
            self.store, self.assessment, evaluation_cutoff_utc=EVALUATION,
        )
        self.assertEqual(len(path), 5)
        self.assertEqual(tuple(point.session_date for point in path),
                         tuple(date(2026, 9, 1) + timedelta(days=i) for i in range(1, 6)))
        self.assertTrue(all(point.contract_symbol == CALL_SYMBOL for point in path))
        self.assertNotIn(self.assessment.observation_id,
                         {point.observation_id for point in path})
        earlier = read_exact_contract_option_path(
            self.store, self.assessment,
            evaluation_cutoff_utc=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
        self.assertEqual(len(earlier), 1)

    def test_after_midnight_utc_quote_keeps_registered_market_session(self) -> None:
        market_session = date(2026, 9, 7)
        quote = datetime(2026, 9, 8, 0, 30, tzinfo=UTC)
        dataset_id = self._dataset("AFTER-HOURS", market_session, quote)
        record = self.store.record_contract_observation(
            thesis_id=self.thesis.thesis_id, run_id=RUN_ID, ticker="ABC",
            contract_symbol=CALL_SYMBOL, option_side="CALL",
            quote_as_of=quote, observed_at=quote + timedelta(minutes=1),
            source_dataset_id=dataset_id, spot=101, strike=100,
            expiration=date(2026, 10, 16), dte=38,
            liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
            bid=2.1, ask=2.3,
        ).record
        path = read_exact_contract_option_path(
            self.store, self.assessment, evaluation_cutoff_utc=EVALUATION,
        )
        matched = [point for point in path if point.observation_id == record.observation_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].session_date, market_session)

    def test_completed_underlying_reader_respects_observation_cutoff(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        rows = [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ]
        prices.ingest("ABC", rows, provider="MARKETDATA", source_kind="TEST")
        before = read_completed_underlying_path(
            prices, self.assessment, evaluation_cutoff_utc=EVALUATION,
            ticker="ABC",
        )
        self.assertEqual(before, ())
        after = read_completed_underlying_path(
            prices, self.assessment,
            evaluation_cutoff_utc=datetime.now(UTC) + timedelta(minutes=1),
            ticker="ABC",
        )
        self.assertEqual(len(after), 5)
        self.assertTrue(all(point.dataset_id for point in after))

    def test_family_capture_matures_only_observable_horizons(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ], provider="MARKETDATA", source_kind="TEST")
        cutoff = datetime.now(UTC) + timedelta(minutes=1)
        first = capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=cutoff, horizons=(1, 5, 10),
        )
        self.assertIsNotNone(first)
        self.assertEqual(first.summary.expected_labels, 2)
        self.assertTrue(first.summary.reconciled)
        self.assertEqual(first.summary.provider_calls, 0)
        self.assertEqual({item.horizon_sessions for item in first.labels}, {1, 5})
        second = capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=cutoff, horizons=(1, 5, 10),
        )
        self.assertIsNone(second)

    def test_batch_is_bounded_and_observation_only(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ], provider="MARKETDATA", source_kind="TEST")
        cutoff = datetime.now(UTC) + timedelta(minutes=1)
        batch = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1, 5, 10),
        )
        self.assertEqual(batch.families_scanned, 1)
        self.assertEqual(batch.families_captured, 1)
        self.assertEqual(batch.labels_appended, 2)
        self.assertEqual(batch.provider_calls, 0)
        self.assertEqual(batch.authority, "OBSERVATION_ONLY")
        self.assertFalse(batch.can_grant_capital)

    def test_later_registered_quote_supersedes_label_append_only(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 2), "open": 101, "high": 103,
             "low": 99, "close": 102, "volume": 1000},
        ], provider="MARKETDATA", source_kind="TEST")
        cutoff = datetime.now(UTC) + timedelta(minutes=1)
        first = capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=cutoff, horizons=(1,),
        )
        old = first.labels[0]
        quote = datetime(2026, 9, 2, 20, 5, tzinfo=UTC)
        dataset_id = self._dataset("LATE-QUOTE", date(2026, 9, 2), quote)
        self.store.record_contract_observation(
            thesis_id=self.thesis.thesis_id, run_id=RUN_ID, ticker="ABC",
            contract_symbol=CALL_SYMBOL, option_side="CALL",
            quote_as_of=quote, observed_at=quote + timedelta(minutes=1),
            source_dataset_id=dataset_id, spot=102, strike=100,
            expiration=date(2026, 10, 16), dte=44,
            liquidity_state=ContractLiquidityState.REVIEWABLE_SPREAD,
            bid=3.0, ask=3.2,
        )
        second = capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=cutoff, horizons=(1,),
        )
        new = second.labels[0]
        self.assertNotEqual(old.label_id, new.label_id)
        self.assertEqual(new.supersedes_label_id, old.label_id)
        self.assertEqual(self.store.doi_outcome_label(old.label_id).to_dict(), old.to_dict())
        self.assertEqual(self.store.latest_outcome_label(
            assessment_id=self.assessment.assessment_id, horizon_sessions=1,
        ).label_id, new.label_id)
        lookup = load_option_outcome_lookup(self.root / "control.sqlite")
        self.assertEqual(lookup[(self.assessment.assessment_id, 1)]["label_id"], new.label_id)
        self.assertIsNone(capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=cutoff, horizons=(1,),
        ))

    def test_partial_path_can_be_corrected_to_complete_after_backfill(self) -> None:
        partial = self._service(
            horizons=(5,),
            read_option_path=lambda _: self.future_options[:4],
        ).labels[0]
        self.assertIs(partial.data_status, OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL)
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ], provider="MARKETDATA", source_kind="TEST")
        corrected = capture_matured_family(
            self.store, prices, family_id=self.family.family_id,
            evaluation_cutoff_utc=datetime.now(UTC) + timedelta(minutes=1),
            horizons=(5,),
        ).labels[0]
        self.assertIs(corrected.data_status, OutcomeDataStatus.COMPLETE)
        self.assertEqual(corrected.supersedes_label_id, partial.label_id)
        self.assertEqual(len(self.store.outcome_labels_for_assessment(
            self.assessment.assessment_id)), 2)
        self.assertEqual(self.store.latest_outcome_label(
            assessment_id=self.assessment.assessment_id,
            horizon_sessions=5,
        ).label_id, corrected.label_id)

    def test_transient_reader_failure_does_not_supersede_valid_label(self) -> None:
        original = self._service(horizons=(1,)).labels[0]

        def fail(_):
            raise RuntimeError("temporary path read failure")

        retry = self._service(horizons=(1,), read_option_path=fail)
        self.assertEqual(retry.labels[0].label_id, original.label_id)
        self.assertEqual(retry.summary.retained_prior_on_reader_error, 1)
        self.assertEqual(len(self.store.outcome_labels_for_assessment(
            self.assessment.assessment_id)), 1)

    def test_thinned_reader_path_does_not_revoke_complete_label(self) -> None:
        original = self._service(horizons=(5,)).labels[0]
        self.assertIs(original.data_status, OutcomeDataStatus.COMPLETE)
        retry = self._service(
            horizons=(5,), read_option_path=lambda _: self.future_options[:4],
        )
        self.assertEqual(retry.labels[0].label_id, original.label_id)
        self.assertEqual(retry.summary.retained_prior_on_reader_error, 1)
        self.assertEqual(len(self.store.outcome_labels_for_assessment(
            self.assessment.assessment_id)), 1)

    def test_unlinked_conflicting_final_labels_are_excluded_from_learning(self) -> None:
        original = self._service(horizons=(1,)).labels[0]
        version = "INDEPENDENT-UNLINKED-CALCULATION"
        conflicting = replace(
            original,
            label_id=outcome_label_identity(
                assessment_id=original.assessment_id,
                horizon_sessions=1,
                outcome_cutoff_utc=original.outcome_cutoff_utc,
                calculation_version=version,
                data_status=original.data_status,
            ),
            calculation_version=version,
        )
        self.store.record_doi_outcome_label(conflicting)
        with self.assertRaises(OptionLifecycleConflict):
            self.store.latest_outcome_label(
                assessment_id=self.assessment.assessment_id,
                horizon_sessions=1,
            )
        self.assertNotIn(
            (self.assessment.assessment_id, 1),
            load_option_outcome_lookup(self.root / "control.sqlite"),
        )

    def test_scheduler_advances_when_family_is_not_yet_mature(self) -> None:
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [{
            "date": date(2026, 9, 1), "open": 100, "high": 101,
            "low": 99, "close": 100, "volume": 1000,
        }], provider="MARKETDATA", source_kind="TEST")
        cutoff = datetime.now(UTC) + timedelta(minutes=1)
        first = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1,),
        )
        second = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1,),
        )
        self.assertEqual(first.families_scanned, 1)
        self.assertEqual(first.families_captured, 0)
        self.assertEqual(second.scan_cycle, 1)
        self.assertEqual(first.cursor_family_id, second.cursor_family_id)

    def test_scheduler_cursor_resumes_and_coverage_reconciles(self) -> None:
        second_family = ContractFamily.create(
            thesis=self.thesis, run_id=RUN_ID, family_policy_version="FAMILY-V2",
            evidence_cutoff_utc=ORIGIN, candidate_symbols=(CALL_SYMBOL,),
            source_dataset_ids=(self.origin_dataset,),
            family_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            created_at=ORIGIN,
        )
        second_family = self.store.record_contract_family(second_family).record
        second_assessment = ContractAssessment.create(
            family_id=second_family.family_id, thesis_id=self.thesis.thesis_id,
            run_id=RUN_ID, contract_symbol=CALL_SYMBOL,
            observation_id=self.assessment.observation_id,
            entry_state=ContractEntryState.CONTRACT_LIMIT_PRICE_REQUIRED,
            applicability_state=ModelApplicabilityState.DETERMINISTIC_ONLY,
            evidence_cutoff_utc=ORIGIN, input_dataset_ids=(self.origin_dataset,),
            calculation_version="ASSESS-V2", feature_version="FEATURE-V1",
            model_version="NOT_EVALUATED", ranking_score_uncalibrated=0.5,
        )
        self.store.record_contract_assessment(second_assessment)
        prices = HistoricalPriceDatabase(self.root / "prices.sqlite")
        prices.initialise()
        prices.ingest("ABC", [
            {"date": date(2026, 9, 1) + timedelta(days=i),
             "open": 100 + i, "high": 102 + i, "low": 99 + i,
             "close": 101 + i, "volume": 1000}
            for i in range(1, 6)
        ], provider="MARKETDATA", source_kind="TEST")
        cutoff = datetime.now(UTC) + timedelta(minutes=1)
        first = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1, 5, 10),
        )
        second = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1, 5, 10),
        )
        self.assertEqual(first.families_scanned, 1)
        self.assertEqual(second.families_scanned, 1)
        self.assertNotEqual(first.cursor_family_id, second.cursor_family_id)
        self.assertEqual(second.coverage_assessments, 2)
        self.assertEqual(second.coverage_expected, 6)
        self.assertEqual(second.coverage_final, 4)
        self.assertEqual(second.coverage_pending, 2)
        self.assertEqual(second.coverage_by_horizon[1]["final"], 2)
        self.assertEqual(second.coverage_by_horizon[10]["pending"], 2)
        third = capture_matured_option_batch(
            self.store, prices, evaluation_cutoff_utc=cutoff,
            current_run_id="NEXT-RUN", candidate_scan_limit=1,
            capture_limit=1, horizons=(1, 5, 10),
        )
        self.assertGreaterEqual(third.scan_cycle, 1)


if __name__ == "__main__":
    unittest.main()
