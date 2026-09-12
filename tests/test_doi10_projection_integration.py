from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
import uuid

from canonical_data.dynamic_options_projection import DynamicOptionsProjectionResolver
from domain.dynamic_options_projection import merge_all_opportunities
from pipeline_interpreter.evidence_resolver import (
    EvidenceResolutionError, IntendedUse, resolve_interpreter_opportunity,
)
from contracts.interpreter_handoff import (
    AUTHORITY_MAP_VERSION, BUNDLE_SCHEMA_VERSION, HandoffValidationError,
    validate_evidence_bundle,
)
from contracts.lab_control import write_final_opportunity_book


class DOI10ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _database(self) -> Path:
        database = self.root / "control_plane.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript("""
                CREATE TABLE doi_contract_families (
                    family_id TEXT, thesis_id TEXT, ticker TEXT,
                    governed_direction TEXT, evidence_cutoff_utc TEXT
                );
                CREATE TABLE doi_contract_assessments (
                    assessment_id TEXT, p_liquidity_3d REAL,
                    p_positive_return_before_horizon REAL,
                    p_target_before_invalidation REAL, model_uncertainty REAL,
                    model_version TEXT
                );
                CREATE TABLE doi_family_rankings (
                    ranking_id TEXT, family_id TEXT,
                    evidence_cutoff_utc TEXT, payload_json TEXT
                );
            """)
            connection.execute(
                "INSERT INTO doi_contract_families VALUES (?,?,?,?,?)",
                ("fam-1", "thesis-1", "ABC", "CALL", "2026-09-10T08:00:00+00:00"),
            )
            connection.execute(
                "INSERT INTO doi_contract_assessments VALUES (?,?,?,?,?,?)",
                ("assess-1", .72, .61, .57, .18, "doi-probability-v1"),
            )
            ranking = {
                "selected_assessment_id": "assess-1",
                "selected_contract_symbol": "O:ABC261016C00100000",
                "selection_reason": "CALIBRATED_POLICY_TOP_RANK",
                "mode": "CALIBRATED_POLICY", "policy_id": "policy-1",
                "evidence_cutoff_utc": "2026-09-10T08:00:00+00:00",
                "input_dataset_ids": ["dataset-1"],
                "ranked_contracts": [
                    {"rank": 1, "contract_symbol": "O:ABC261016C00100000", "score": .8,
                     "score_kind": "CALIBRATED_POLICY_UTILITY", "explanation": "top", "selected": True},
                    {"rank": 2, "contract_symbol": "O:ABC261016C00105000", "score": .7,
                     "score_kind": "CALIBRATED_POLICY_UTILITY", "explanation": "alternative", "selected": False},
                ],
            }
            connection.execute(
                "INSERT INTO doi_family_rankings VALUES (?,?,?,?)",
                ("rank-1", "fam-1", "2026-09-10T08:00:00+00:00", json.dumps(ranking)),
            )
            connection.commit()
        return database

    def test_projection_is_exact_and_advisory(self):
        source = {
            "run_id": "run-1", "ticker": "ABC", "thesis_id": "thesis-1",
            "governed_direction": "CALL", "selected_contract_symbol": "O:ABC261016C00100000",
            "final_action": "BUY_NOW", "capital_permission": "YES",
        }
        output = DynamicOptionsProjectionResolver(self._database()).project_row(source)
        self.assertEqual(output["doi_projection_state"], "CALIBRATED")
        self.assertEqual(output["doi_contract_alignment"], "MATCH")
        self.assertEqual(output["doi_p_liquidity_3d"], .72)
        self.assertEqual(output["doi_authority"], "ADVISORY_ONLY")
        self.assertEqual(output["final_action"], "BUY_NOW")
        self.assertEqual(output["capital_permission"], "YES")
        self.assertEqual(len(json.loads(output["doi_alternatives_json"])), 2)

    def test_different_preference_does_not_replace_governed_contract(self):
        source = {"ticker": "ABC", "thesis_id": "thesis-1", "governed_direction": "CALL",
                  "selected_contract_symbol": "O:ABC261016C00105000"}
        output = DynamicOptionsProjectionResolver(self._database()).project_row(source)
        self.assertEqual(output["doi_contract_alignment"], "DIFFERENT_ADVISORY")
        self.assertEqual(output["selected_contract_symbol"], source["selected_contract_symbol"])

    def test_inactive_store_is_explicit_and_population_is_preserved(self):
        rows = [{"ticker": "ABC"}, {"ticker": "XYZ"}]
        output = DynamicOptionsProjectionResolver(self.root / "missing.sqlite").project_rows(rows)
        self.assertEqual(len(output), 2)
        self.assertTrue(all(row["doi_projection_state"] == "DATA_UNAVAILABLE" for row in output))

    def test_lab_merge_preserves_full_population(self):
        full = [
            {"run_id": "r", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1", "final_action": "WAIT"},
            {"run_id": "r", "ticker": "XYZ", "thesis_id": "t2", "trade_idea_id": "i2", "final_action": "WAIT"},
        ]
        actionable = [
            {"run_id": "r", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1",
             "lab_schema_version": "lab_signal_book_v3",
             "final_action": "BUY_NOW", "current_contract_bid": 1.25}
        ]
        rows, reconciliation = merge_all_opportunities(full, actionable)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["final_action"], "WAIT")
        self.assertEqual(rows[0]["current_contract_bid"], 1.25)
        self.assertNotEqual(rows[0].get("lab_schema_version"), "lab_signal_book_v3")
        self.assertEqual(rows[0]["lab_actionable_overlay_state"], "APPLIED")
        self.assertFalse(rows[1]["lab_actionable_handoff_member"])
        self.assertTrue(reconciliation["population_preserved"])

    def test_lab_merge_cannot_overwrite_direction_or_contract_identity(self):
        full = [{
            "run_id": "r", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1",
            "governed_direction": "CALL", "selected_contract_symbol": "ABC261016C00100000",
            "final_action": "WAIT", "capital_permission": "NO",
        }]
        forged = [{
            "run_id": "r", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1",
            "governed_direction": "PUT", "selected_contract_symbol": "ABC261016P00100000",
            "final_action": "BUY_NOW", "capital_permission": "YES", "current_contract_bid": 2.0,
        }]
        rows, reconciliation = merge_all_opportunities(full, forged)
        self.assertEqual(rows[0]["governed_direction"], "CALL")
        self.assertEqual(rows[0]["selected_contract_symbol"], "ABC261016C00100000")
        self.assertEqual(rows[0]["final_action"], "WAIT")
        self.assertEqual(rows[0]["capital_permission"], "NO")
        self.assertNotIn("current_contract_bid", rows[0])
        self.assertFalse(rows[0]["lab_actionable_handoff_member"])
        self.assertEqual(rows[0]["lab_actionable_overlay_state"], "REJECTED_IDENTITY_MISMATCH")
        self.assertEqual(reconciliation["status"], "PARTIAL")
        self.assertEqual(reconciliation["actionable_rows_rejected"], 1)

    def test_lab_merge_retains_other_tickers_when_one_overlay_is_invalid(self):
        full = [
            {"run_id": "r", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1"},
            {"run_id": "r", "ticker": "XYZ", "thesis_id": "t2", "trade_idea_id": "i2"},
        ]
        actionable = [
            {"run_id": "r", "ticker": "ABC", "thesis_id": "wrong", "trade_idea_id": "i1"},
            {"run_id": "r", "ticker": "XYZ", "thesis_id": "t2", "trade_idea_id": "i2",
             "current_contract_ask": 3.5},
        ]
        rows, reconciliation = merge_all_opportunities(full, actionable)
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]["lab_actionable_handoff_member"])
        self.assertTrue(rows[1]["lab_actionable_handoff_member"])
        self.assertEqual(rows[1]["current_contract_ask"], 3.5)
        self.assertEqual(reconciliation["actionable_rows_overlaid"], 1)
        self.assertEqual(reconciliation["actionable_rows_rejected"], 1)

    def test_contract_symbol_strike_expiry_and_side_mismatch_is_disclosed(self):
        source = {
            "ticker": "ABC", "thesis_id": "thesis-1", "governed_direction": "PUT",
            "selected_contract_symbol": "ABC261016C00100000",
            "strike": 105.0, "expiry": "2026-10-23",
        }
        output = DynamicOptionsProjectionResolver(self._database()).project_row(source)
        self.assertEqual(output["doi_projection_state"], "DATA_INCONSISTENT")
        self.assertEqual(output["doi_governed_contract_identity_state"], "MISMATCH")
        self.assertIn("STRIKE_MISMATCH", output["doi_governed_contract_identity_reason"])
        self.assertIn("EXPIRY_MISMATCH", output["doi_governed_contract_identity_reason"])
        self.assertIn("SIDE_MISMATCH", output["doi_governed_contract_identity_reason"])

    def test_interpreter_can_resolve_non_actionable_for_advisory_review(self):
        run = self.root / "r1" / "intelligence_lab"
        run.mkdir(parents=True)
        book = {"lab_schema_version": "lab_signal_book_v2", "candidate_count": 1,
                "rows": [{"run_id": "r1", "ticker": "XYZ", "final_action": "WAIT",
                          "doi_projection_state": "NOT_EVALUATED"}]}
        (run / "final_opportunity_book_r1.json").write_text(json.dumps(book), encoding="utf-8")
        result = resolve_interpreter_opportunity("xyz", run_id="r1", runs_dir=self.root)
        self.assertEqual(result.authority, "ADVISORY_ONLY")
        self.assertEqual(result.book_row["final_action"], "WAIT")
        self.assertEqual(result.provider_calls, 0)

    def test_full_book_resolver_cannot_be_used_as_execution_authority(self):
        with self.assertRaises(EvidenceResolutionError) as caught:
            resolve_interpreter_opportunity(
                "ABC", run_id="r1", runs_dir=self.root,
                intended_use=IntendedUse.EXECUTABLE_SESSION,
            )
        self.assertEqual(caught.exception.code, "FULL_BOOK_USE_NOT_ADVISORY")

    def test_interpreter_bundle_accepts_lineage_bound_advisory_projection(self):
        governed = {
            "run_id": "r1", "ticker": "ABC", "thesis_id": "t1", "trade_idea_id": "i1",
            "selected_structure_id": "s1", "selected_quote_snapshot_id": "q1",
            "selected_contract_symbol": "ABC261016C00100000",
            "doi_projection_state": "CALIBRATED", "doi_family_id": "f1",
            "doi_ranking_id": "rank1", "doi_evidence_cutoff_utc": "2026-09-10T08:00:00+00:00",
            "doi_authority": "ADVISORY_ONLY", "doi_decision_authority": "NONE",
            "doi_execution_authority": "HUMAN_ONLY",
        }
        bundle = {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "authority_map_version": AUTHORITY_MAP_VERSION,
            "bundle_id": str(uuid.uuid4()), "bundle_created_utc": "2026-09-10T08:01:00+00:00",
            "pipeline_mode": "MORNING_VALIDATION", **{key: governed[key] for key in (
                "run_id", "ticker", "thesis_id", "trade_idea_id", "selected_structure_id",
                "selected_contract_symbol", "selected_quote_snapshot_id",
            )},
            "authority_map": {"doi_authority": "ADVISORY_ONLY"}, "freshness_map": {},
            "governed_record": governed,
        }
        self.assertEqual(validate_evidence_bundle(bundle)["ticker"], "ABC")
        forged = {**bundle, "governed_record": {**governed, "doi_decision_authority": "MODEL"}}
        with self.assertRaises(HandoffValidationError):
            validate_evidence_bundle(forged)

    def test_final_book_writer_projects_every_row_without_doi_store(self):
        runs_dir = self.root / "data" / "output" / "runs"
        result = write_final_opportunity_book(
            "r1",
            [{
                "ticker": "ABC", "governed_direction": "CALL",
                "underlying_price": 100, "target_spot": 110,
                "invalidation_spot": 90,
            }],
            {"pipeline_mode": "COMPLETED_SESSION"},
            runs_dir,
            sync_interpreter=False,
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["rows"][0]["doi_projection_state"], "DATA_UNAVAILABLE")
        self.assertTrue(result["reconciliation"]["doi_population_preserved"])
        self.assertTrue(Path(result["json_path"]).is_file())

    def test_lab_renders_eil_as_advisory_observation_not_stop(self):
        project = Path(__file__).resolve().parents[1]
        ui = (project / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
        backend = (project / "intelligence-lab" / "intelligence_lab.py").read_text(encoding="utf-8")
        eil_function = ui[ui.index("function getEilDisplay"):ui.index("function normaliseHorizonLabel")]
        self.assertNotIn("fd_verdict", eil_function)
        self.assertNotIn("final_decision_advisory_verdict", eil_function)
        self.assertIn("const eilAdv  = true", ui)
        self.assertIn("display==='NOT_EVALUATED'?'N/A':'OBS'", ui)
        self.assertNotIn('"NEGATIVE_RR": "NO_TRADE"', backend)
        self.assertIn('"NEGATIVE_RR": "REVIEW_ECONOMICS"', backend)

    def test_lab_distinguishes_missing_projection_and_renders_lineage(self):
        project = Path(__file__).resolve().parents[1]
        ui = (project / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("s['doi_projection_state'] || 'DATA_UNAVAILABLE'", ui)
        self.assertIn("DOI_NOT_RUN_OR_FIELDS_ABSENT", ui)
        self.assertNotIn("s['doi_governed_contract_symbol'] || s['selected_contract_symbol']", ui)
        for field in (
            "doi_projection_version", "doi_family_id", "doi_ranking_id",
            "doi_preferred_assessment_id", "doi_policy_id",
            "doi_input_dataset_ids_json", "doi_evidence_cutoff_utc",
            "doi_probability_model_id", "doi_governed_contract_identity_state",
            "doi_governed_contract_identity_reason",
        ):
            self.assertIn(field, ui)

    def test_advisory_opportunity_resolver_is_exported_and_routed(self):
        project = Path(__file__).resolve().parents[1]
        resolver = (project / "pipeline_interpreter" / "evidence_resolver.py").read_text(encoding="utf-8")
        commands = (project / "pipeline_interpreter" / "pipeline_interpreter_commands.py").read_text(encoding="utf-8")
        self.assertIn('"resolve_interpreter_opportunity"', resolver[resolver.index("__all__ ="):])
        self.assertIn("def _msi_cmd_review", commands)
        self.assertIn('elif cmd=="/review"', commands)
        self.assertIn("IntendedUse.EOD_REVIEW", commands)


if __name__ == "__main__":
    unittest.main()
