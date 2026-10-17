"""G4 history correction (ACK approved 17 Oct 2026): option observations recorded with a model delta are superseded,
append-only, by the provider's delta from the MarketData chain quoted at the same time.

Design: Enhancements/options_valuation_review/G4_HESTON_GREEKS_ROOT_CAUSE_AND_DESIGN_20261017.md §5.5 / §8.3(a).
Before G4, Options Intelligence registered the selected contract (LIVE_OPTION, selected_option_quote_v1) with the
Heston ATM-variance delta and the store recorded it as a MARKETDATA observation.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.errors import DatasetValidationError
from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState,
    MonitorState,
    OptionLiquidityLifecycleStore,
    ThesisState,
)
from canonical_data.option_outcome_maturation import read_exact_contract_option_path
from canonical_data.registry import CanonicalRegistry
from scripts import correct_observation_greeks_g4 as g4

RUN_14, RUN_15, RUN_15B = "20261014_220000", "20261015_225021", "20261015_230000"
S14, S15 = date(2026, 10, 14), date(2026, 10, 15)
Q14 = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
Q15 = datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc)
CONTRACT = "EVTL261120P00007500"
MODEL_DELTA, PROVIDER_DELTA = -0.9753150809662972, -0.3842
CORRECTION_SUFFIX = "G4"
CORRECTION_RUN = f"{RUN_15}_G4"   # one correction run per corrected run


class ObservationGreekCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = CanonicalRegistry(self.root / "control_plane.sqlite")
        self.registry.initialise()
        for run, session in ((RUN_14, S14), (RUN_15, S15)):
            self.registry.register_run(run, "EVENING", session)
        self.store = OptionLiquidityLifecycleStore(self.registry)
        self.store.initialise()
        self.store.record_thesis_event(
            thesis_id="EVTL:PUT:2026-10-14:OLM2", event_key="EOD-CREATED", run_id=RUN_14, ticker="EVTL",
            direction="PUT", thesis_state=ThesisState.ACTIVE, monitor_state=MonitorState.ACTIVE,
            reason_code="LIQUIDITY_PENDING", structural_target=6.0, invalidation_spot=9.0,
            horizon_end_date=date(2026, 11, 6),
        )
        self.chain14 = self._dataset("chain14", DatasetType.OPTION_CHAIN, S14, Q14, RUN_14,
                                     [self._quote(-0.35, Q14)])
        self.chain15 = self._dataset("chain15", DatasetType.OPTION_CHAIN, S15, Q15, RUN_15,
                                     [self._quote(PROVIDER_DELTA, Q15)])
        self.live15 = self._dataset("live15", DatasetType.LIVE_OPTION, S15, Q15, RUN_15,
                                    [self._quote(MODEL_DELTA, Q15)],
                                    extra={"contract_symbol": CONTRACT, "source_chain_dataset_id": self.chain15},
                                    schema="selected_option_quote_v1")
        self.origin = self._observe(RUN_14, self.chain14, Q14, -0.35)
        self.recorded = self._observe(RUN_15, self.live15, Q15, MODEL_DELTA)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _quote(delta: float, at: datetime) -> dict:
        return {"symbol": CONTRACT, "delta": delta, "bid": 1.9, "ask": 2.1, "implied_vol": 8.6296,
                "quote_timestamp_utc": at.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def _dataset(self, name, dataset_type, session, at, run, rows, *, extra=None, schema="option_chain_v2",
                 ticker="EVTL", provider="MARKETDATA") -> str:
        payload = json.dumps(rows).encode("utf-8")
        path = self.root / f"{name}.json"
        path.write_bytes(payload)
        self.registry.register_dataset(DatasetRecord(
            dataset_id=name, dataset_type=dataset_type, instrument_id=ticker, session_date=session,
            scope=DataScope(start_date=session, end_date=session, dte_min=None, dte_max=None, sides=("PUT",),
                            extra=tuple((extra or {}).items())),
            provider=provider, content_hash=hashlib.sha256(payload).hexdigest(),
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path), observed_at=at, as_of=at,
            adjustment_convention="RAW_OPTION_CONTRACT", schema_version=schema, source_run_id=run,
        ))
        return name

    def _observe(self, run, dataset_id, at, delta):
        return self.store.record_contract_observation(
            thesis_id="EVTL:PUT:2026-10-14:OLM2", run_id=run, ticker="EVTL", contract_symbol=CONTRACT,
            option_side="PUT", quote_as_of=at, source_dataset_id=dataset_id, spot=7.4, strike=7.5,
            expiration=date(2026, 11, 20), dte=35, liquidity_state=ContractLiquidityState.LIQUIDITY_PENDING,
            observed_at=at, delta=delta, bid=1.9, ask=2.1, spread_pct=0.1, volume=10, open_interest=100,
            iv=8.6296,
        ).record

    def _rows(self):
        with self.registry.connection() as connection:
            return [dict(r) for r in connection.execute(
                "SELECT * FROM option_contract_observations ORDER BY observed_at, observation_id")]

    def _apply(self):
        planned, skipped = g4.plan_corrections(self.registry)
        g4.apply_corrections(self.store, planned, run_suffix=CORRECTION_SUFFIX)
        return planned, skipped

    def test_a_model_delta_recorded_as_provider_is_planned_for_correction_with_the_chain_delta(self):
        planned, _ = g4.plan_corrections(self.registry)
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]["observation_id"], self.recorded.observation_id)
        self.assertAlmostEqual(planned[0]["recorded_delta"], MODEL_DELTA)
        self.assertAlmostEqual(planned[0]["provider_delta"], PROVIDER_DELTA)
        self.assertEqual(planned[0]["chain_dataset_id"], self.chain15)

    def test_the_correction_is_appended_and_supersedes_the_recorded_observation(self):
        self._apply()
        rows = self._rows()
        original = next(r for r in rows if r["observation_id"] == self.recorded.observation_id)
        correction = next(r for r in rows if r["supersedes_event_id"] == self.recorded.observation_id)
        self.assertAlmostEqual(original["delta"], MODEL_DELTA)          # history is never rewritten
        self.assertAlmostEqual(correction["delta"], PROVIDER_DELTA)
        self.assertEqual(correction["source_dataset_id"], self.chain15)
        self.assertEqual(correction["correction_reason"], g4.CORRECTION_REASON)
        self.assertEqual(correction["correction_state"], "CORRECTED")
        self.assertEqual(correction["run_id"], CORRECTION_RUN)
        self.assertEqual(correction["corrected_by_run_id"], CORRECTION_RUN)
        for field in ("thesis_id", "contract_symbol", "quote_as_of", "bid", "ask", "iv", "spot", "strike",
                      "expiration", "dte", "volume", "open_interest", "liquidity_state"):
            self.assertEqual(correction[field], original[field], field)

    def test_readers_see_only_the_corrected_observation(self):
        self._apply()
        latest = self.store.latest_observation("EVTL:PUT:2026-10-14:OLM2")
        self.assertAlmostEqual(latest.delta, PROVIDER_DELTA)
        with self.registry.connection() as connection:
            connection.execute(
                "INSERT INTO doi_contract_families(family_id, thesis_id, thesis_version, run_id, ticker, "
                "governed_direction, origin_spot, origin_timestamp_utc, planned_hold_sessions, planned_hold_source, "
                "thesis_evidence_cutoff_utc, family_policy_version, evidence_cutoff_utc, family_state, created_at, "
                "decision_authority, can_change_direction, can_invalidate_thesis, can_grant_capital, payload_hash) "
                "VALUES ('F1','EVTL:PUT:2026-10-14:OLM2',1,?, 'EVTL','PUT',7.4,'2026-10-14T20:00:00Z',5,'TEST',"
                "'2026-10-14T20:00:00Z','T','2026-10-14T20:00:00Z','ACTIVE','2026-10-14T20:00:00Z','NONE',0,0,0,'h')",
                (RUN_14,))
        assessment = SimpleNamespace(observation_id=self.origin.observation_id, evidence_cutoff_utc=Q14,
                                     contract_symbol=CONTRACT, family_id="F1")
        path = read_exact_contract_option_path(self.store, assessment,
                                               evaluation_cutoff_utc=datetime(2026, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(len(path), 1)
        self.assertNotEqual(path[0].observation_id, self.recorded.observation_id)

    def test_the_same_quote_recorded_by_two_runs_is_corrected_once_per_run(self):
        """Live apply 17 Oct: one quote recorded by two evening runs. Each run gets its own correction run."""
        self.registry.register_run(RUN_15B, "EVENING", S15)
        again = self._observe(RUN_15B, self.live15, Q15, MODEL_DELTA)
        self._apply()
        corrections = {r["supersedes_event_id"]: r for r in self._rows() if r["supersedes_event_id"]}
        self.assertEqual(set(corrections), {self.recorded.observation_id, again.observation_id})
        self.assertEqual(corrections[self.recorded.observation_id]["run_id"], f"{RUN_15}_G4")
        self.assertEqual(corrections[again.observation_id]["run_id"], f"{RUN_15B}_G4")
        for row in corrections.values():
            self.assertAlmostEqual(row["delta"], PROVIDER_DELTA)

    def test_the_correction_is_idempotent(self):
        self._apply()
        planned, _ = self._apply()
        self.assertEqual(planned, [])
        self.assertEqual(sum(1 for r in self._rows() if r["supersedes_event_id"]), 1)

    def test_an_observation_that_already_agrees_with_the_chain_is_left_alone(self):
        live = self._dataset("live15b", DatasetType.LIVE_OPTION, S15, Q15, RUN_15,
                             [self._quote(PROVIDER_DELTA, Q15)],
                             extra={"contract_symbol": CONTRACT, "source_chain_dataset_id": self.chain15},
                             schema="selected_option_quote_v1")
        self.registry.register_run(RUN_15B, "EVENING", S15)
        agreeing = self._observe(RUN_15B, live, Q15, PROVIDER_DELTA)
        planned, skipped = g4.plan_corrections(self.registry)
        self.assertNotIn(agreeing.observation_id, [p["observation_id"] for p in planned])
        self.assertEqual(skipped["ALREADY_PROVIDER_DELTA"], 1)

    def test_no_chain_quote_at_the_observation_time_means_no_correction(self):
        moved = datetime(2026, 10, 15, 19, 45, tzinfo=timezone.utc)
        chain = self._dataset("chain15_early", DatasetType.OPTION_CHAIN, S15, moved, RUN_15,
                              [self._quote(PROVIDER_DELTA, moved)])
        live = self._dataset("live15c", DatasetType.LIVE_OPTION, S15, Q15, RUN_15, [self._quote(MODEL_DELTA, Q15)],
                             extra={"contract_symbol": CONTRACT, "source_chain_dataset_id": chain},
                             schema="selected_option_quote_v1")
        self.registry.register_run(RUN_15B, "EVENING", S15)
        unmatched = self._observe(RUN_15B, live, Q15, MODEL_DELTA)
        planned, skipped = g4.plan_corrections(self.registry)
        self.assertNotIn(unmatched.observation_id, [p["observation_id"] for p in planned])
        self.assertEqual(skipped["NO_CHAIN_QUOTE_AT_QUOTE_TIME"], 1)

    def test_the_store_refuses_a_correction_not_sourced_from_that_tickers_marketdata_chain(self):
        other = self._dataset("chain_other", DatasetType.OPTION_CHAIN, S15, Q15, RUN_15,
                              [self._quote(PROVIDER_DELTA, Q15)], ticker="ALT")
        self.registry.register_run(CORRECTION_RUN, "CORRECTION", S15)
        for source in (other, self.live15):
            with self.assertRaises(DatasetValidationError):
                self.store.record_observation_greek_correction(
                    superseded_observation_id=self.recorded.observation_id, delta=PROVIDER_DELTA,
                    source_dataset_id=source, corrected_by_run_id=CORRECTION_RUN,
                    correction_reason=g4.CORRECTION_REASON)


if __name__ == "__main__":
    unittest.main()
