from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.direction_governance import resolve_governed_direction
from contracts.options_liquidity_execution_guard import evaluate_olm_execution_guard
from morning_handoff_finalizer import (
    MorningHandoffError,
    _execution_lab_mismatches,
    _sync_and_verify,
    finalize_morning_handoff,
    sync_verified_morning_handoff,
)


RUN_ID = "20990101_010101"


def _governed_direction(ticker: str, side: str) -> dict:
    return resolve_governed_direction(
        ticker=ticker,
        run_id=RUN_ID,
        discovery_direction=side,
        governed_direction=side,
        governed_basis=f"test_preCOR={side}",
        row={},
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, *, preserve_authority: bool = True):
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / RUN_ID
    morning_path = run_dir / "morning_validation" / f"morning_validated_trades_{RUN_ID}.csv"
    source_rows = [
        {
            "run_id": RUN_ID,
            "ticker": "AAA",
            "verdict": "GO",
            "morning_execution_permission": "GO_LIMIT",
            "lifecycle_contract_version": "options-liquidity-lifecycle-v1",
            "thesis_state": "ACTIVE",
            "liquidity_state": "EXECUTABLE_NOW",
            "morning_transition_state": "EXECUTABLE_NOW",
            "remaining_runway_state": "THESIS_ACTIVE",
            "executable_now": True,
            **_governed_direction("AAA", "CALL"),
        },
        {
            "run_id": RUN_ID,
            "ticker": "BBB",
            "verdict": "BLOCK",
            "morning_execution_permission": "NOT_ELIGIBLE",
            "lifecycle_contract_version": "options-liquidity-lifecycle-v1",
            "thesis_state": "INVALIDATED",
            "liquidity_state": "EXECUTABLE_NOW",
            "morning_transition_state": "THESIS_INVALIDATED",
            "remaining_runway_state": "THESIS_INVALIDATED",
            "executable_now": False,
            **_governed_direction("BBB", "PUT"),
        },
    ]
    _write_csv(morning_path, source_rows)
    interpreter_dir = tmp_path / "interpreter"

    def fake_gate(signals, run_id, output_dir):
        rows = []
        for row in signals:
            decision = evaluate_olm_execution_guard(row, require_contract=True)
            rows.append({
                **row,
                **decision.as_fields(),
                "final_action": "BUY_SMALL" if row["ticker"] == "AAA" else "BLOCK",
            })
        gated_path = Path(output_dir) / f"execution_gated_{run_id}.csv"
        _write_csv(gated_path, rows)
        return rows, {"gated_csv": str(gated_path), "action_counts": {"BUY_SMALL": 1, "BLOCK": 1}}

    def fake_manifest(run_id, runs_dir, pipeline_mode="EOD"):
        return {"run_id": run_id, "pipeline_mode": pipeline_mode}

    def fake_lab(run_id, signals, run_manifest, runs_dir, **_kwargs):
        rows = [
            {
                **row,
                "lab_verdict": (
                    "GO_LIMIT" if preserve_authority and row["ticker"] == "AAA" else "BLOCKED"
                ),
            }
            for row in signals
        ]
        lab_dir = Path(runs_dir) / run_id / "intelligence_lab"
        final_path = lab_dir / f"final_opportunity_book_{run_id}.csv"
        triage_path = lab_dir / f"lab_triage_view_{run_id}.csv"
        _write_csv(final_path, rows)
        _write_csv(triage_path, rows)
        return {
            "rows": rows,
            "csv_path": str(final_path),
            "triage_csv_path": str(triage_path),
            "candidate_count": len(rows),
        }

    def fake_sync(source, verbose=True, force=False):
        interpreter_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, interpreter_dir / Path(source).name)
        return True

    patches = (
        patch("execution_gate.run_execution_gate", side_effect=fake_gate),
        patch("contracts.lab_control.write_final_run_manifest", side_effect=fake_manifest),
        patch("contracts.lab_control.write_final_opportunity_book", side_effect=fake_lab),
        patch("pipeline_interpreter.ma_inputs_sync.sync_file", side_effect=fake_sync),
        patch("pipeline_interpreter.ma_inputs_sync.MA_PIPELINE_OUT", interpreter_dir),
    )
    return runs_dir, source_rows, interpreter_dir, patches


class MorningHandoffFinalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        # These are the legacy four-file compatibility tests.  MSI-active
        # identity and atomic-publication behaviour has its own dedicated
        # materializer tests; do not let the persistent production rollout
        # flags silently change this fixture's contract.
        self._msi_legacy_mode = patch.dict(
            "os.environ",
            {
                "MSI_LAB_V3_VIEW": "0",
                "MSI_INTERPRETER_RESOLVER": "0",
            },
        )
        self._msi_legacy_mode.start()

    def tearDown(self) -> None:
        self._msi_legacy_mode.stop()

    def test_known_false_promotions_are_detected_by_exact_reconciliation(self) -> None:
        tickers = ["QCOM", "SW", "SBUX", "BR", "TRMB", "CG", "LOW"]
        gated = [
            {"ticker": ticker, "final_action": "CONTRACT_REPAIR", "contract_symbol": f"{ticker}990119C00100000"}
            for ticker in tickers
        ]
        lab = [
            {**row, "lab_verdict": "GO_LIMIT"}
            for row in gated
        ]
        mismatches = _execution_lab_mismatches(gated, lab)
        self.assertEqual(len(mismatches), len(tickers))
        self.assertTrue(all("EXPECTED_CONTRACT_REPAIR_GOT_GO_LIMIT" in item for item in mismatches))

    def test_completed_run_reconciles_and_syncs_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runs_dir, rows, interpreter_dir, patches = _fixture(tmp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                summary = finalize_morning_handoff(RUN_ID, rows, runs_dir=runs_dir)

            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["api_requests"], 0)
            self.assertEqual(summary["source_rows"], 2)
            self.assertEqual(summary["execution_rows"], 2)
            self.assertEqual(summary["lab_rows"], 2)
            self.assertEqual(summary["source_actionable"], 1)
            self.assertEqual(summary["lab_actionable"], 1)
            self.assertEqual(len(summary["interpreter_sync"]), 4)
            self.assertTrue(all(item["verified"] for item in summary["interpreter_sync"]))
            self.assertTrue((interpreter_dir / f"final_opportunity_book_{RUN_ID}.csv").exists())
            self.assertTrue(Path(summary["summary_path"]).exists())

    def test_deferred_sync_publishes_only_after_explicit_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runs_dir, rows, interpreter_dir, patches = _fixture(tmp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                summary = finalize_morning_handoff(
                    RUN_ID,
                    rows,
                    runs_dir=runs_dir,
                    sync_interpreter=False,
                )
                self.assertEqual(summary["interpreter_sync"], [])
                self.assertFalse(interpreter_dir.exists())

                synced = sync_verified_morning_handoff(summary)

            self.assertEqual(len(synced), 4)
            self.assertTrue(all(item["verified"] for item in synced))
            self.assertTrue(
                (interpreter_dir / f"final_opportunity_book_{RUN_ID}.csv").exists()
            )

    def test_recovery_requires_existing_morning_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MorningHandoffError, "input not found"):
                finalize_morning_handoff(RUN_ID, runs_dir=Path(directory) / "runs")

    def test_handoff_fails_closed_when_lab_loses_morning_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs_dir, rows, _, patches = _fixture(Path(directory), preserve_authority=False)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                with self.assertRaisesRegex(MorningHandoffError, "authority reconciliation failed"):
                    finalize_morning_handoff(RUN_ID, rows, runs_dir=runs_dir)

    def test_handoff_fails_when_lab_promotes_contract_repair_to_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runs_dir, rows, _, patches = _fixture(Path(directory))

            def false_promotion(run_id, signals, run_manifest, runs_dir, **_kwargs):
                lab_rows = [dict(row) for row in signals]
                lab_rows[0]["lab_verdict"] = "GO_LIMIT"
                lab_rows[1]["final_action"] = "CONTRACT_REPAIR"
                lab_rows[1]["lab_verdict"] = "GO_LIMIT"
                lab_dir = Path(runs_dir) / run_id / "intelligence_lab"
                final_path = lab_dir / f"final_opportunity_book_{run_id}.csv"
                triage_path = lab_dir / f"lab_triage_view_{run_id}.csv"
                _write_csv(final_path, lab_rows)
                _write_csv(triage_path, lab_rows)
                return {"rows": lab_rows, "csv_path": str(final_path), "triage_csv_path": str(triage_path)}

            with patches[0], patches[1], patch(
                "contracts.lab_control.write_final_opportunity_book",
                side_effect=false_promotion,
            ), patches[3], patches[4]:
                with self.assertRaisesRegex(MorningHandoffError, "authority reconciliation failed"):
                    finalize_morning_handoff(RUN_ID, rows, runs_dir=runs_dir)

    def test_both_entrypoints_use_shared_mandatory_finalizer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        morning_source = (root / "morning_gate.py").read_text(encoding="utf-8")
        orchestrator_source = (root / "intelligent_orchestrator.py").read_text(encoding="utf-8")
        premarket = orchestrator_source[
            orchestrator_source.index("def premarket_workflow") : orchestrator_source.index(
                "def enforce_handoff_conflict_guard"
            )
        ]

        self.assertIn("results = run_morning_gate", morning_source)
        self.assertIn("sync_interpreter=False", morning_source)
        self.assertIn("sync_verified_morning_handoff(handoff)", morning_source)
        self.assertIn("finalize_morning_handoff(", premarket)
        self.assertIn("return False", premarket)
        self.assertNotIn("final_csv_path", premarket)

    def test_final_opportunity_book_routes_to_pipeline_outputs(self) -> None:
        from pipeline_interpreter.ma_inputs_sync import MA_PIPELINE_OUT, _route_file

        for filename in (
            "final_opportunity_book_20990101_010101.csv",
            "execution_gated_20990101_010101.csv",
            "execution_actionable_20990101_010101.csv",
        ):
            with self.subTest(filename=filename):
                destination, label = _route_file(Path(filename))
                self.assertEqual(destination, MA_PIPELINE_OUT)
                self.assertEqual(label, "pipeline_output")

    def test_sync_survives_pipeline_interpreter_module_directory_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sync_dir = root / "pipeline_interpreter"
            sync_dir.mkdir()
            (sync_dir / "ma_inputs_sync.py").write_text(
                "from pathlib import Path\n"
                "import shutil\n"
                "MA_PIPELINE_OUT = Path(__file__).parent / 'MA_Inputs' / 'pipeline_outputs'\n"
                "def sync_file(source, verbose=True, force=False):\n"
                "    MA_PIPELINE_OUT.mkdir(parents=True, exist_ok=True)\n"
                "    shutil.copy2(source, MA_PIPELINE_OUT / Path(source).name)\n"
                "    return True\n",
                encoding="utf-8",
            )
            source = root / "morning_validated_trades_test.csv"
            source.write_text("ticker\nAAA\n", encoding="utf-8")
            conflicting_module = types.ModuleType("pipeline_interpreter")

            with patch.dict(
                sys.modules,
                {
                    "pipeline_interpreter": conflicting_module,
                    "pipeline_interpreter.ma_inputs_sync": None,
                },
            ), patch(
                "morning_handoff_finalizer.REPO_ROOT", root
            ):
                result = _sync_and_verify([source])

            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["verified"])


if __name__ == "__main__":
    unittest.main()
