from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from canonical_data.contracts import DataScope, DatasetRequest, DatasetType
from canonical_data.registry import CanonicalRegistry
from canonical_data.request_ledger import RequestLedger
from canonical_data.run_plan import (
    RequestedAction,
    RunPlanStore,
    contract_episode_identity,
    evidence_identity,
    quote_observation_identity,
    resolve_run_plan,
    thesis_identity,
    validation_event_identity,
)


REPO = Path(__file__).resolve().parents[1]


class RunPlanResolutionTests(unittest.TestCase):
    def test_no_thesis_builds_from_last_completed_session(self) -> None:
        plan = resolve_run_plan(
            as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
            authorised_tickers=("msft", "AAPL"),
        )
        self.assertEqual(plan.session_state, "PREMARKET")
        self.assertEqual(plan.last_completed_session, "2026-09-04")
        self.assertEqual(plan.resolved_action, "BUILD_THESIS")
        self.assertEqual(plan.execution_authority_ceiling, "EOD_PREPARED")
        self.assertEqual(plan.authorised_ticker_worklists["DISCOVERY"], ("AAPL", "MSFT"))

    def test_current_thesis_premarket_validates_without_profile_fabrication(self) -> None:
        plan = resolve_run_plan(
            as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
            existing_thesis_id="thesis-1",
            existing_thesis_session=date(2026, 9, 4),
            authorised_tickers=("AAPL",),
        )
        self.assertEqual(plan.resolved_action, "VALIDATE")
        self.assertNotIn("DEVELOPING_MARKET_PROFILE", plan.stages_to_run)
        self.assertNotIn(
            "DEVELOPING_SESSION",
            {item.evidence_state for item in plan.datasets_required},
        )
        self.assertEqual(plan.run_condition, "PREOPEN_THESIS_CHECK")
        self.assertNotIn("SURVIVOR_OPTION_REFRESH", plan.stages_to_run)
        self.assertNotIn(
            "EXACT_OPTION_QUOTE",
            {item.dataset_type for item in plan.datasets_required},
        )

    def test_regular_session_adds_developing_profile(self) -> None:
        plan = resolve_run_plan(
            as_of_utc=datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
            existing_thesis_id="thesis-1",
            existing_thesis_session=date(2026, 9, 4),
            authorised_tickers=("AAPL",),
        )
        self.assertIn("DEVELOPING_MARKET_PROFILE", plan.stages_to_run)
        intraday = next(item for item in plan.datasets_required if item.dataset_type == "INTRADAY_BAR")
        self.assertEqual(intraday.evidence_state, "DEVELOPING_SESSION")

    def test_after_hours_waits_for_provider_finalisation(self) -> None:
        common = dict(
            as_of_utc=datetime(2026, 9, 8, 21, tzinfo=timezone.utc),
            existing_thesis_id="thesis-2",
            existing_thesis_session=date(2026, 9, 8),
            authorised_tickers=("AAPL",),
        )
        partial = resolve_run_plan(**common, provider_session_finalised=False)
        finalised = resolve_run_plan(**common, provider_session_finalised=True)
        self.assertEqual(partial.resolved_action, "VALIDATE")
        self.assertEqual(finalised.resolved_action, "FINALISE")

    def test_closed_weekend_reuses_current_thesis_without_requests(self) -> None:
        plan = resolve_run_plan(
            as_of_utc=datetime(2026, 9, 5, 12, tzinfo=timezone.utc),
            existing_thesis_id="thesis-friday",
            existing_thesis_session=date(2026, 9, 4),
            authorised_tickers=("AAPL",),
        )
        self.assertEqual(plan.session_state, "CLOSED")
        self.assertEqual(plan.resolved_action, "AUTO")
        self.assertEqual(plan.stages_to_run, ())
        self.assertEqual(plan.estimated_physical_requests, 0)

    def test_fixed_inputs_are_deterministic_and_cutoff_change_is_new_invocation(self) -> None:
        common = dict(
            as_of_utc=datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
            existing_thesis_id="thesis-1",
            existing_thesis_session=date(2026, 9, 4),
            authorised_tickers=("AAPL", "MSFT"),
            pipeline_run_id="run-fixed",
        )
        first = resolve_run_plan(**common)
        retry = resolve_run_plan(**common)
        changed = resolve_run_plan(
            **{**common, "evidence_cutoff_utc": common["as_of_utc"] - timedelta(minutes=1)}
        )
        self.assertEqual(first.plan_hash, retry.plan_hash)
        self.assertEqual(first.invocation_id, retry.invocation_id)
        self.assertNotEqual(first.invocation_id, changed.invocation_id)

    def test_cache_coverage_reduces_physical_request_estimate(self) -> None:
        plan = resolve_run_plan(
            as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
            authorised_tickers=("AAPL", "MSFT"),
            cache_coverage={"DAILY_OHLCV": 2, "INTRADAY_BAR": 1, "OPTION_CHAIN": 0},
        )
        self.assertEqual(plan.estimated_physical_requests, 3)


class IdentityAndPersistenceTests(unittest.TestCase):
    def test_domain_identities_are_deterministic_and_change_with_material_input(self) -> None:
        thesis = thesis_identity(
            ticker="aapl",
            completed_session=date(2026, 9, 4),
            governed_direction="call",
            evidence_ids=("dataset-b", "dataset-a"),
            model_version="v1",
            thesis_version=1,
        )
        self.assertEqual(
            thesis,
            thesis_identity(
                ticker="AAPL",
                completed_session=date(2026, 9, 4),
                governed_direction="CALL",
                evidence_ids=("dataset-a", "dataset-b"),
                model_version="v1",
                thesis_version=1,
            ),
        )
        evidence = evidence_identity(
            evidence_type="market_profile",
            input_dataset_ids=("dataset-a",),
            calculation_version="mp-v1",
            content_hash="ABC",
        )
        contract = contract_episode_identity(
            thesis_id=thesis,
            strategy="long_call",
            occ_symbols=("O:AAPL260918C00200000",),
        )
        quote = quote_observation_identity(
            contract_episode_id=contract,
            provider_observed_at_utc=datetime(2026, 9, 8, 14, tzinfo=timezone.utc),
            content_hash="DEF",
        )
        validation = validation_event_identity(
            thesis_id=thesis,
            evidence_cutoff_utc=datetime(2026, 9, 8, 14, tzinfo=timezone.utc),
            underlying_observation_id="underlying-1",
            quote_observation_id=quote,
            developing_profile_evidence_id=evidence,
        )
        changed = validation_event_identity(
            thesis_id=thesis,
            evidence_cutoff_utc=datetime(2026, 9, 8, 14, 1, tzinfo=timezone.utc),
            underlying_observation_id="underlying-1",
            quote_observation_id=quote,
            developing_profile_evidence_id=evidence,
        )
        self.assertNotEqual(validation, changed)
        self.assertTrue(thesis.startswith("thesis_"))
        self.assertTrue(evidence.startswith("evidence_"))
        self.assertTrue(contract.startswith("contract_"))
        self.assertTrue(quote.startswith("quote_"))

    def test_dataset_request_carries_session_cutoff_calendar_and_invocation(self) -> None:
        cutoff = datetime(2026, 9, 4, 20, tzinfo=timezone.utc)
        request = DatasetRequest(
            run_id="run-1",
            requesting_stage="discovery",
            dataset_type=DatasetType.DAILY_OHLCV,
            instrument_id="aapl",
            session_date=date(2026, 9, 4),
            scope=DataScope(start_date=date(2026, 9, 1), end_date=date(2026, 9, 4)),
            invocation_id="inv-1",
            evidence_cutoff_utc=cutoff,
            exchange_calendar="xnys",
            evidence_state="completed_session",
        )
        self.assertEqual(request.invocation_id, "inv-1")
        self.assertEqual(request.exchange_calendar, "XNYS")
        self.assertEqual(request.evidence_state, "COMPLETED_SESSION")
        self.assertEqual(request.evidence_cutoff_utc, cutoff)
        self.assertEqual(len(request.request_fingerprint), 64)

    def test_naive_cutoff_is_rejected(self) -> None:
        with self.assertRaisesRegex(Exception, "timezone-aware"):
            DatasetRequest(
                "run", "stage", DatasetType.DAILY_OHLCV, "AAPL", date(2026, 9, 4),
                evidence_cutoff_utc=datetime(2026, 9, 4, 20),
            )

    def test_request_ledger_persists_dynamic_request_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry = CanonicalRegistry(Path(temporary) / "control.sqlite")
            registry.initialise()
            registry.register_run("run-1", "PLAN_TEST", date(2026, 9, 4))
            request = DatasetRequest(
                "run-1", "stage", DatasetType.DAILY_OHLCV, "AAPL", date(2026, 9, 4),
                invocation_id="inv-1",
                evidence_cutoff_utc=datetime(2026, 9, 4, 20, tzinfo=timezone.utc),
                evidence_state="COMPLETED_SESSION",
            )
            ledger = RequestLedger(registry)
            request_id = ledger.start(request)
            entry = next(item for item in ledger.entries("run-1") if item["request_id"] == request_id)
            self.assertEqual(entry["invocation_id"], "inv-1")
            self.assertEqual(entry["evidence_state"], "COMPLETED_SESSION")
            self.assertEqual(entry["exchange_calendar"], "XNYS")
            self.assertEqual(entry["request_fingerprint"], request.request_fingerprint)

    def test_control_plane_v1_ledger_migrates_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.sqlite"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """CREATE TABLE api_request_ledger(
                    request_id TEXT PRIMARY KEY, run_id TEXT, stage TEXT, ticker TEXT,
                    dataset_type TEXT, scope_fingerprint TEXT, provider TEXT,
                    resolution TEXT, dataset_id TEXT, physical_request_count INTEGER,
                    retry_count INTEGER, reason TEXT, started_at TEXT, completed_at TEXT)"""
                )
                connection.execute(
                    "INSERT INTO api_request_ledger VALUES "
                    "('req-1','run-1','STAGE','AAPL','DAILY_OHLCV','scope',NULL," 
                    "'CACHE_HIT',NULL,0,0,'','2026-09-04T20:00:00Z',NULL)"
                )
                connection.commit()
            finally:
                connection.close()
            registry = CanonicalRegistry(path)
            with self.assertRaisesRegex(RuntimeError, "schema migration required"):
                registry.initialise()
            registry.initialise(allow_migration=True)
            with registry.connection() as migrated:
                columns = {
                    row[1] for row in migrated.execute("PRAGMA table_info(api_request_ledger)")
                }
                row = migrated.execute(
                    "SELECT invocation_id, request_fingerprint FROM api_request_ledger "
                    "WHERE request_id='req-1'"
                ).fetchone()
                migration = migrated.execute(
                    "SELECT from_version, to_version, detail_json "
                    "FROM schema_migration_log WHERE migration_id = ?",
                    ("cds_control_plane_v1_to_v2",),
                ).fetchone()
            self.assertTrue(
                {"invocation_id", "evidence_cutoff_utc", "exchange_calendar", "evidence_state", "request_fingerprint"}
                <= columns
            )
            self.assertEqual(tuple(row), ("run-1", "LEGACY:req-1"))
            self.assertEqual(tuple(migration[:2]), (
                "cds_control_plane_v1", "cds_control_plane_v2"
            ))
            self.assertEqual(
                set(json.loads(migration["detail_json"])["added_columns"]),
                {"invocation_id", "evidence_cutoff_utc", "exchange_calendar", "evidence_state", "request_fingerprint"},
            )

    def test_partial_control_plane_migration_is_detected_and_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "partial.sqlite"
            registry = CanonicalRegistry(path)
            registry.initialise()
            registry.register_run("run-1", "TEST", date(2026, 9, 4))
            with registry.connection() as connection:
                connection.execute(
                    "INSERT INTO api_request_ledger(" 
                    "request_id,run_id,stage,ticker,dataset_type,scope_fingerprint," 
                    "resolution,started_at) VALUES " 
                    "('req-1','run-1','STAGE','AAPL','DAILY_OHLCV','scope'," 
                    "'CACHE_HIT','2026-09-04T20:00:00Z')"
                )
                connection.execute(
                    "DELETE FROM schema_metadata WHERE schema_version = ?",
                    ("cds_control_plane_v2",),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO schema_metadata VALUES "
                    "('cds_control_plane_v1','2026-09-04T20:00:00Z')"
                )
            status = registry.migration_status()
            self.assertTrue(status["required"])
            self.assertEqual(status["pending_columns"], ())
            self.assertEqual(status["legacy_rows_pending_backfill"], 1)
            with self.assertRaisesRegex(RuntimeError, "schema migration required"):
                registry.initialise()

            registry.initialise(allow_migration=True)
            self.assertFalse(registry.migration_status()["required"])
            with registry.connection() as connection:
                row = connection.execute(
                    "SELECT invocation_id, request_fingerprint "
                    "FROM api_request_ledger WHERE request_id='req-1'"
                ).fetchone()
                detail = json.loads(connection.execute(
                    "SELECT detail_json FROM schema_migration_log WHERE migration_id=?",
                    ("cds_control_plane_v1_to_v2",),
                ).fetchone()[0])
            self.assertEqual(tuple(row), ("run-1", "LEGACY:req-1"))
            self.assertTrue(detail["resumed_partial_migration"])

    def test_store_is_append_only_and_identical_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = RunPlanStore(Path(temporary) / "plans.sqlite")
            plan = resolve_run_plan(
                as_of_utc=datetime(2026, 9, 8, 15, tzinfo=timezone.utc),
                existing_thesis_id="thesis-1",
                existing_thesis_session=date(2026, 9, 4),
                authorised_tickers=("AAPL",),
            )
            self.assertTrue(store.persist(plan))
            self.assertFalse(store.persist(plan))
            self.assertEqual(store.load(plan.invocation_id)["plan_hash"], plan.plan_hash)
            forged = replace(plan, plan_hash="")
            object.__setattr__(forged, "expected_outputs", ("forged",))
            object.__setattr__(forged, "plan_hash", forged.compute_hash())
            with self.assertRaisesRegex(ValueError, "different immutable plan content"):
                store.persist(forged)

    def test_plan_only_cli_has_no_filesystem_side_effect_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            before = set(Path(temporary).iterdir())
            # The acceptance runtime is intentionally a clean Python 3.13
            # executable with the production venv supplied on PYTHONPATH.
            # Keep dependency locations while excluding the repository root;
            # the script must still bootstrap its own source imports.
            import os
            dependency_paths = [
                entry
                for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep)
                if entry and Path(entry).resolve() != REPO.resolve()
            ]
            child_environment = dict(os.environ)
            if dependency_paths:
                child_environment["PYTHONPATH"] = os.pathsep.join(dependency_paths)
            else:
                child_environment.pop("PYTHONPATH", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "resolve_run_plan.py"),
                    "--as-of-utc", "2026-09-08T15:00:00Z",
                    "--existing-thesis-id", "thesis-1",
                    "--existing-thesis-session", "2026-09-04",
                    "--ticker", "AAPL",
                ],
                cwd=temporary,
                check=True,
                capture_output=True,
                text=True,
                env=child_environment,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["resolved_action"], "VALIDATE")
            self.assertEqual(set(Path(temporary).iterdir()), before)


if __name__ == "__main__":
    unittest.main()
