from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.dynamic_options_production import run_completed_session_doi
from canonical_data.option_liquidity_lifecycle import (
    MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from tools.doi11_production_readiness import assess_doi11


RUN_ID = "20260910_200000"
SESSION = date(2026, 9, 10)
CUTOFF = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)


class DOI11ProductionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "data" / "canonical" / "control_plane.sqlite"
        self.registry = CanonicalRegistry(self.database)
        self.registry.initialise()
        self.registry.register_run(RUN_ID, "EVENING", SESSION)

    def tearDown(self):
        self.temp.cleanup()

    def _register_chain(self, ticker: str, direction: str, strike: float):
        symbol = f"{ticker}261016{'C' if direction == 'CALL' else 'P'}{int(strike*1000):08d}"
        rows = [{
            "symbol": symbol, "right": direction[0], "strike": strike,
            "expiration_date": "2026-10-16", "underlying_price": 100.0,
            "bid": 2.0, "ask": 2.2, "bid_size": 10, "ask_size": 12,
            "volume": 40, "open_interest": 120, "implied_vol": .30,
            "delta": .5 if direction == "CALL" else -.5,
            "quote_timestamp_utc": CUTOFF.isoformat(),
        }]
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / f"{ticker}.json"
        path.write_bytes(payload)
        dataset_id = hashlib.sha256(f"{ticker}-chain".encode()).hexdigest()
        self.registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id, dataset_type=DatasetType.OPTION_CHAIN,
            instrument_id=ticker, session_date=SESSION,
            scope=DataScope(start_date=SESSION, end_date=SESSION, dte_min=1, dte_max=90, sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=hashlib.sha256(payload).hexdigest(),
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=CUTOFF, as_of=CUTOFF,
            adjustment_convention="RAW_OPTION_CONTRACT", schema_version="option_chain_v2",
            source_run_id=RUN_ID,
        ))

    def _register_wide_call_chain(self, ticker: str, count: int = 20):
        rows = []
        for offset in range(count):
            strike = 91.0 + offset
            rows.append({
                "symbol": f"{ticker}261016C{int(strike*1000):08d}",
                "right": "C", "strike": strike, "expiration_date": "2026-10-16",
                "underlying_price": 100.0, "bid": 2.0, "ask": 2.2,
                "bid_size": 10, "ask_size": 12, "volume": offset,
                "open_interest": offset, "implied_vol": .30, "delta": .5,
                "quote_timestamp_utc": CUTOFF.isoformat(),
            })
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        path = self.root / f"{ticker}-wide.json"
        path.write_bytes(payload)
        self.registry.register_dataset(DatasetRecord(
            dataset_id=hashlib.sha256(f"{ticker}-wide-chain".encode()).hexdigest(),
            dataset_type=DatasetType.OPTION_CHAIN, instrument_id=ticker,
            session_date=SESSION,
            scope=DataScope(start_date=SESSION, end_date=SESSION, dte_min=1, dte_max=90, sides=("CALL", "PUT")),
            provider="MARKETDATA", content_hash=hashlib.sha256(payload).hexdigest(),
            completeness_status=CompletenessStatus.COMPLETE, storage_uri=str(path),
            observed_at=CUTOFF, as_of=CUTOFF, adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="option_chain_v2", source_run_id=RUN_ID,
        ))

    def test_call_and_put_complete_canonical_cycle_without_provider_fetch(self):
        self._register_chain("AAA", "CALL", 100.0)
        self._register_chain("BBB", "PUT", 100.0)
        upstream = OptionLiquidityLifecycleStore(self.registry)
        upstream.initialise()
        upstream.record_thesis_event(
            thesis_id="AAA:CALL:1", event_key="UPSTREAM_OLM", run_id=RUN_ID,
            ticker="AAA", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="UPSTREAM_GOVERNED",
            structural_target=110, invalidation_spot=95, recorded_at=CUTOFF,
        )
        source = self.root / "options.csv"
        pd.DataFrame([
            {"ticker": "AAA", "thesis_id": "AAA:CALL:1", "governed_direction": "CALL",
             "underlying_price": 100, "target_spot": 110, "invalidation_spot": 95,
             "planned_hold_sessions": 5, "planned_hold_source": "HORIZON_ROUTER",
             "quote_timestamp_utc": CUTOFF.isoformat(), "ev3_rate_used": .045},
            {"ticker": "BBB", "thesis_id": "BBB:PUT:1", "governed_direction": "PUT",
             "underlying_price": 100, "target_spot": 90, "invalidation_spot": 105,
             "planned_hold_sessions": 5, "planned_hold_source": "HORIZON_ROUTER",
             "quote_timestamp_utc": CUTOFF.isoformat(), "ev3_rate_used": .045},
        ]).to_csv(source, index=False)
        result = run_completed_session_doi(
            run_id=RUN_ID, options_csv=source, registry_path=self.database,
            report_path=self.root / "report.json",
        )
        self.assertEqual(result.unique_tickers, 2)
        self.assertEqual(result.retained_opportunities, 2)
        self.assertEqual(result.family_rows, 2)
        self.assertEqual(result.assessed_families, 2)
        self.assertEqual(result.ranked_families, 2)
        self.assertEqual(result.lifecycle_families, 2)
        self.assertEqual(result.physical_fetch_count, 0)
        self.assertEqual(result.exception_count, 0)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doi_contract_families").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doi_family_rankings").fetchone()[0], 2)

        # A same-run restart over identical immutable inputs must be idempotent.
        replay = run_completed_session_doi(
            run_id=RUN_ID, options_csv=source, registry_path=self.database,
            report_path=self.root / "report-replay.json",
        )
        self.assertEqual(replay.exception_count, 0)
        self.assertEqual(replay.ranked_families, 2)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doi_contract_families").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doi_family_rankings").fetchone()[0], 2)

    def test_data_defects_and_non_directional_rows_are_retained(self):
        source = self.root / "options.csv"
        pd.DataFrame([
            {"ticker": "BAD", "governed_direction": "CALL", "underlying_price": 100,
             "planned_hold_sessions": 5, "quote_timestamp_utc": CUTOFF.isoformat()},
            {"ticker": "ND", "governed_direction": "STRANGLE", "underlying_price": 50},
        ]).to_csv(source, index=False)
        result = run_completed_session_doi(
            run_id=RUN_ID, options_csv=source, registry_path=self.database,
            report_path=self.root / "report.json",
        )
        self.assertEqual(result.unique_tickers, 2)
        self.assertEqual(result.retained_opportunities, 2)
        self.assertEqual(result.deleted_opportunities, 0)
        self.assertEqual(result.exception_count, 1)
        self.assertEqual(result.counts_by_state["NOT_APPLICABLE_NON_DIRECTIONAL"], 1)
        self.assertEqual(result.counts_by_state["DATA_EXCEPTION_RETAINED"], 1)

    def test_wide_chain_retains_full_taxonomy_but_bounds_production_valuation(self):
        self._register_wide_call_chain("WIDE")
        source = self.root / "wide-options.csv"
        pd.DataFrame([{
            "ticker": "WIDE", "thesis_id": "WIDE:CALL:1", "governed_direction": "CALL",
            "underlying_price": 100, "target_spot": 112, "invalidation_spot": 95,
            "planned_hold_sessions": 5, "planned_hold_source": "HORIZON_ROUTER",
            "quote_timestamp_utc": CUTOFF.isoformat(), "ev3_rate_used": .045,
        }]).to_csv(source, index=False)
        result = run_completed_session_doi(
            run_id=RUN_ID, options_csv=source, registry_path=self.database,
            report_path=self.root / "wide-report.json",
        )
        self.assertEqual(result.family_candidates_total, 20)
        self.assertEqual(result.bounded_candidates_total, 12)
        self.assertEqual(result.assessed_families, 1)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doi_contract_assessments").fetchone()[0], 12)

    def test_runtime_is_reuse_only_and_orchestration_order_is_governed(self):
        root = Path(__file__).resolve().parents[1]
        runtime = json.loads((root / "config" / "doi_runtime.json").read_text(encoding="utf-8"))
        self.assertIs(runtime["enabled"], True)
        self.assertIs(runtime["canonical_reuse_only"], True)
        self.assertIs(runtime["provider_fetch_allowed"], False)
        self.assertEqual(runtime["decision_authority"], "NONE")
        self.assertEqual(runtime["execution_authority"], "HUMAN_ONLY")

        source = (root / "intelligent_orchestrator.py").read_text(encoding="utf-8")
        horizon = source.index("_oi_horizon_patched = patch_horizon_fields_into_csv")
        doi = source.index("run_dynamic_options_intelligence(canonical_run_id)", horizon)
        ev3 = source.index("_ev3_shadow_ok = run_ev3_governed_shadow", doi)
        self.assertLess(horizon, doi)
        self.assertLess(doi, ev3)

    def test_acceptance_assessor_distinguishes_evening_from_morning_acceptance(self):
        self._register_chain("AAA", "CALL", 100.0)
        run_root = self.root / "data" / "output" / "runs" / RUN_ID
        source = run_root / "options" / f"options_intelligence_{RUN_ID}.csv"
        source.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{
            "ticker": "AAA", "thesis_id": "AAA:CALL:1", "governed_direction": "CALL",
            "underlying_price": 100, "target_spot": 110, "invalidation_spot": 95,
            "planned_hold_sessions": 5, "planned_hold_source": "HORIZON_ROUTER",
            "quote_timestamp_utc": CUTOFF.isoformat(), "ev3_rate_used": .045,
        }]).to_csv(source, index=False)
        report = source.parent / f"dynamic_options_intelligence_{RUN_ID}.json"
        run_completed_session_doi(
            run_id=RUN_ID, options_csv=source, registry_path=self.database,
            report_path=report,
        )
        config = self.root / "config" / "doi_runtime.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({
            "enabled": True, "canonical_reuse_only": True,
            "provider_fetch_allowed": False, "decision_authority": "NONE",
            "execution_authority": "HUMAN_ONLY",
        }), encoding="utf-8")
        book = run_root / "intelligence_lab" / f"final_opportunity_book_{RUN_ID}.json"
        book.parent.mkdir(parents=True, exist_ok=True)
        book.write_text(json.dumps({
            "lab_schema_version": "lab_signal_book_v2",
            "candidate_count": 1, "rows": [{
                "ticker": "AAA", "doi_projection_state": "DETERMINISTIC_UNCALIBRATED",
                "doi_decision_authority": "NONE", "doi_execution_authority": "HUMAN_ONLY",
            }],
        }), encoding="utf-8")

        evening = assess_doi11(run_id=RUN_ID, project_root=self.root)
        self.assertEqual(evening["status"], "EVENING_ACCEPTED_AWAITING_MORNING")
        strict = assess_doi11(run_id=RUN_ID, project_root=self.root, require_morning=True)
        self.assertEqual(strict["status"], "AWAITING_LIVE_CYCLE")

        morning = run_root / "morning_validation" / f"morning_validated_trades_{RUN_ID}.csv"
        morning.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"ticker": "AAA"}]).to_csv(morning, index=False)
        accepted = assess_doi11(run_id=RUN_ID, project_root=self.root, require_morning=True)
        self.assertEqual(accepted["status"], "PRODUCTION_ACCEPTED")


if __name__ == "__main__":
    unittest.main()
