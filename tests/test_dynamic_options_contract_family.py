from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from canonical_data.contracts import (
    CompletenessStatus,
    DataScope,
    DatasetRecord,
    DatasetType,
)
from canonical_data.dynamic_options_bridge import GovernedOptionObservation
from canonical_data.dynamic_options_family import (
    ThesisConditionedContractFamilyGenerator,
)
from canonical_data.option_liquidity_lifecycle import (
    MonitorState,
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.contract_family_generation import FamilyCandidateState
from domain.dynamic_options_intelligence import (
    ObservationAcquisitionDecision,
    OptionObservationKind,
    UnderlyingThesisRef,
)


UTC = timezone.utc
RUN_ID = "20260910_200000"
SESSION = date(2026, 9, 10)
CUTOFF = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)


def _symbol(side: str, strike: float, expiry: str = "261016") -> str:
    return f"ABC{expiry}{'C' if side == 'CALL' else 'P'}{int(strike * 1000):08d}"


class DynamicOptionsContractFamilyTests(unittest.TestCase):
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

    def _thesis(self, direction: str = "CALL") -> UnderlyingThesisRef:
        target = 110.0 if direction == "CALL" else 90.0
        invalidation = 95.0 if direction == "CALL" else 105.0
        thesis_id = f"ABC-{direction}-DOI4"
        self.store.record_thesis_event(
            thesis_id=thesis_id,
            event_key="DOI4-FAMILY-ORIGIN",
            run_id=RUN_ID,
            ticker="ABC",
            direction=direction,
            thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE,
            reason_code="GOVERNED_THESIS",
            structural_target=target,
            invalidation_spot=invalidation,
            horizon_end_date=date(2026, 10, 1),
        )
        return UnderlyingThesisRef(
            thesis_id=thesis_id,
            thesis_version=1,
            ticker="ABC",
            governed_direction=direction,
            origin_spot=100.0,
            origin_timestamp_utc=CUTOFF - timedelta(hours=1),
            target_spot=target,
            invalidation_spot=invalidation,
            planned_hold_sessions=10,
            planned_hold_source="HORIZON_ROUTER",
            evidence_cutoff_utc=CUTOFF,
        )

    def _register(self, rows: list[dict[str, object]]) -> str:
        encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / "chain.json"
        path.write_bytes(encoded)
        content_hash = hashlib.sha256(encoded).hexdigest()
        dataset_id = hashlib.sha256(b"doi4-test-chain").hexdigest()
        self.registry.register_dataset(
            DatasetRecord(
                dataset_id=dataset_id,
                dataset_type=DatasetType.OPTION_CHAIN,
                instrument_id="ABC",
                session_date=SESSION,
                scope=DataScope(
                    start_date=SESSION,
                    end_date=SESSION,
                    dte_min=1,
                    dte_max=90,
                    sides=("CALL", "PUT"),
                ),
                provider="MARKETDATA",
                content_hash=content_hash,
                completeness_status=CompletenessStatus.COMPLETE,
                storage_uri=str(path),
                observed_at=CUTOFF,
                as_of=CUTOFF,
                adjustment_convention="RAW_OPTION_CONTRACT",
                schema_version="option_chain_v2",
                source_run_id=RUN_ID,
            )
        )
        return dataset_id

    def _observation(self, rows: list[dict[str, object]]) -> GovernedOptionObservation:
        dataset_id = self._register(rows)
        return GovernedOptionObservation(
            ticker="ABC",
            observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=dataset_id,
            provider="MARKETDATA",
            as_of_utc=CUTOFF,
            frame=pd.DataFrame(rows),
            resolution="CANONICAL_REUSE",
            acquisition=ObservationAcquisitionDecision(
                should_fetch=False, reason="REUSE_CANONICAL_EVIDENCE"
            ),
            physical_fetch_count=0,
        )

    @staticmethod
    def _base(side: str, strike: float, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "symbol": _symbol(side, strike),
            "right": "C" if side == "CALL" else "P",
            "strike": strike,
            "expiration_date": "2026-10-16",
            "underlying_price": 100.0,
            "bid": 1.0,
            "ask": 1.2,
            "volume": 10,
            "open_interest": 100,
        }
        row.update(overrides)
        return row

    def test_call_family_keeps_temporary_liquidity_defects_and_excludes_only_structure(self) -> None:
        duplicate = self._base("CALL", 115.0)
        rows = [
            self._base("CALL", 100.0, open_interest=0, volume=0),
            self._base("CALL", 105.0, bid=0.0, ask=1.0),
            self._base("CALL", 110.0, bid=None, ask=None, volume=None, open_interest=None),
            self._base("PUT", 100.0),
            {"symbol": "NOT-OCC", "right": "C", "strike": 100.0},
            self._base("CALL", 120.0, bid=2.0, ask=1.0),
            self._base("CALL", 125.0, bid=-1.0, ask=1.0),
            self._base("CALL", 130.0, expiration_date="2026-09-11", symbol=_symbol("CALL", 130.0, "260911")),
            {**self._base("CALL", 135.0), "strike": 134.0},
            duplicate,
            dict(duplicate),
        ]
        thesis = self._thesis("CALL")
        result = ThesisConditionedContractFamilyGenerator(
            self.store, max_display_candidates=3
        ).generate(
            thesis=thesis,
            observation=self._observation(rows),
            run_id=RUN_ID,
        )
        self.assertEqual(result.summary.source_observations, len(rows))
        self.assertEqual(result.summary.family_candidates, 3)
        self.assertEqual(result.summary.two_sided_candidates, 1)
        self.assertEqual(result.summary.monitor_one_sided, 1)
        self.assertEqual(result.summary.monitor_no_quote, 1)
        self.assertEqual(result.summary.retained_low_open_interest, 2)
        self.assertEqual(result.summary.retained_zero_volume, 1)
        self.assertEqual(set(result.family.candidate_symbols), {
            _symbol("CALL", 100.0), _symbol("CALL", 105.0), _symbol("CALL", 110.0)
        })
        self.assertEqual(len(result.display_symbols), 3)
        self.assertTrue(all(item.option_side != "PUT" or not item.is_family_candidate for item in result.taxonomy))
        excluded_reasons = result.summary.counts_by_exclusion
        for reason in (
            "WRONG_OPTION_SIDE",
            "INVALID_OCC_IDENTITY",
            "CROSSED_QUOTE",
            "NEGATIVE_QUOTE",
            "INSUFFICIENT_SESSION_RUNWAY",
            "IDENTITY_FIELD_MISMATCH",
            "DUPLICATE_CONTRACT_AMBIGUOUS",
        ):
            self.assertGreater(excluded_reasons.get(reason, 0), 0)

    def test_put_path_is_symmetric_and_does_not_change_thesis(self) -> None:
        rows = [
            self._base("PUT", 100.0, open_interest=1, volume=0),
            self._base("PUT", 95.0, bid=0.0, ask=1.0),
            self._base("CALL", 100.0),
        ]
        thesis = self._thesis("PUT")
        result = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=thesis,
            observation=self._observation(rows),
            run_id=RUN_ID,
        )
        self.assertEqual(result.summary.family_candidates, 2)
        self.assertEqual(result.family.thesis.governed_direction, "PUT")
        self.assertFalse(result.family.can_change_direction)
        self.assertFalse(result.family.can_invalidate_thesis)
        self.assertFalse(result.family.can_grant_capital)
        self.assertTrue(all("P" in symbol for symbol in result.family.candidate_symbols))

    def test_ordinary_spread_oi_and_volume_are_never_structural_gates(self) -> None:
        rows = [
            self._base("CALL", 90.0, bid=0.01, ask=10.0, open_interest=0, volume=0),
            self._base("CALL", 100.0, bid=None, ask=2.0, open_interest=None, volume=None),
            self._base("CALL", 140.0, bid=None, ask=None, open_interest=1, volume=0),
        ]
        result = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=self._thesis("CALL"),
            observation=self._observation(rows),
            run_id=RUN_ID,
        )
        self.assertEqual(result.summary.family_candidates, 3)
        self.assertFalse(any(item.structural_exclusions for item in result.taxonomy))

    def test_complete_taxonomy_and_bounded_display_round_trip_idempotently(self) -> None:
        rows = [
            self._base("CALL", strike, expiration_date=expiry, symbol=_symbol("CALL", strike, occ))
            for strike, expiry, occ in (
                (90.0, "2026-10-16", "261016"),
                (100.0, "2026-10-16", "261016"),
                (110.0, "2026-11-20", "261120"),
                (120.0, "2026-12-18", "261218"),
            )
        ]
        thesis = self._thesis("CALL")
        observation = self._observation(rows)
        generator = ThesisConditionedContractFamilyGenerator(
            self.store, max_display_candidates=2
        )
        first = generator.generate(thesis=thesis, observation=observation, run_id=RUN_ID)
        second = generator.generate(thesis=thesis, observation=observation, run_id=RUN_ID)
        self.assertEqual(first.family.family_id, second.family.family_id)
        self.assertEqual(first.display_symbols, second.display_symbols)
        self.assertEqual(len(first.display_symbols), 2)
        stored = self.store.contract_family(first.family.family_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(
            len(stored.metadata["complete_candidate_taxonomy"]), len(rows)
        )
        self.assertEqual(stored.metadata["display_symbols"], list(first.display_symbols))
        self.assertEqual(stored.metadata["display_policy"], "DIVERSIFIED_COVERAGE_NOT_RANKING")

    def test_unavailable_chain_persists_data_insufficient_family_without_row_loss(self) -> None:
        thesis = self._thesis("CALL")
        observation = GovernedOptionObservation(
            ticker="ABC",
            observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=None,
            provider="CANONICAL",
            as_of_utc=None,
            frame=pd.DataFrame(),
            resolution="DORMANT_ACQUISITION_SUPPRESSED",
            acquisition=ObservationAcquisitionDecision(
                should_fetch=False, reason="DORMANT_ACQUISITION_SUPPRESSED"
            ),
            physical_fetch_count=0,
        )
        result = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=thesis, observation=observation, run_id=RUN_ID
        )
        self.assertEqual(result.summary.source_observations, 0)
        self.assertEqual(result.family.family_state.value, "DATA_INSUFFICIENT")
        self.assertEqual(
            result.family.metadata["generation_reason"],
            "DORMANT_ACQUISITION_SUPPRESSED",
        )

    def test_later_chain_uses_a_new_evaluation_cutoff_without_overwriting_no_data(self) -> None:
        thesis = self._thesis("CALL")
        unavailable = GovernedOptionObservation(
            ticker="ABC",
            observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=None,
            provider="CANONICAL",
            as_of_utc=CUTOFF,
            frame=pd.DataFrame(),
            resolution="CANONICAL_CHAIN_UNAVAILABLE",
            acquisition=ObservationAcquisitionDecision(
                should_fetch=False, reason="CANONICAL_CHAIN_UNAVAILABLE"
            ),
            physical_fetch_count=0,
        )
        generator = ThesisConditionedContractFamilyGenerator(self.store)
        missing = generator.generate(
            thesis=thesis, observation=unavailable, run_id=RUN_ID
        )
        available = generator.generate(
            thesis=thesis,
            observation=self._observation([self._base("CALL", 100.0)]),
            run_id=RUN_ID,
            evaluation_cutoff_utc=CUTOFF + timedelta(seconds=1),
        )
        self.assertNotEqual(missing.family.family_id, available.family.family_id)
        self.assertEqual(available.summary.family_candidates, 1)
        self.assertIsNotNone(self.store.contract_family(missing.family.family_id))
        self.assertIsNotNone(self.store.contract_family(available.family.family_id))

    def test_missing_values_remain_null_not_economic_zero(self) -> None:
        result = ThesisConditionedContractFamilyGenerator(self.store).generate(
            thesis=self._thesis("CALL"),
            observation=self._observation([
                self._base("CALL", 100.0, bid=None, ask=None, volume=None, open_interest=None)
            ]),
            run_id=RUN_ID,
        )
        item = result.taxonomy[0]
        self.assertIsNone(item.bid)
        self.assertIsNone(item.ask)
        self.assertIsNone(item.volume)
        self.assertIsNone(item.open_interest)
        self.assertEqual(item.state, FamilyCandidateState.MONITOR_NO_QUOTE)


if __name__ == "__main__":
    unittest.main()
