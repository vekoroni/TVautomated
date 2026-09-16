from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import intelligent_orchestrator
from tests.test_worker3_macro_ticker_context import RUN, SESSION, _hash, _packet, _row


class Worker3MacroOrchestratorTests(unittest.TestCase):
    def test_run_manifest_is_atomic_reconciled_and_advisory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runs = root / "runs"
            run_dir = runs / RUN
            rows = [_row(), {**_row("BAD", "CALL"), "governed_direction": ""}]
            for row in rows:
                row["lab_schema_version"] = "lab_signal_book_v4"
            (run_dir / "intelligence_lab").mkdir(parents=True)
            (run_dir / "run_meta.json").write_text(json.dumps({
                "dynamic_plan": {"last_completed_session": SESSION},
            }), encoding="utf-8")
            (run_dir / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").write_text(
                json.dumps({
                    "lab_schema_version": "lab_signal_book_v4",
                    "run_id": RUN,
                    "candidate_count": len(rows),
                    "rows": rows,
                }),
                encoding="utf-8",
            )
            packet = _packet()
            packet["created_at_utc"] = "2026-09-10T20:00:00Z"
            packet_hash = _hash(packet)
            materialized = {
                "packet": packet,
                "reference": {
                    "packet_id": packet["packet_id"],
                    "path": "interpreter/interpreter_macro_context.json",
                    "sha256": packet_hash,
                },
            }
            with (
                patch.object(intelligent_orchestrator.cfg, "RUNS_DIR", runs),
                patch.object(intelligent_orchestrator.cfg, "MACRO_DIR", root / "macro"),
                patch(
                    "contracts.interpreter_macro_context.materialize_interpreter_macro_context",
                    return_value=materialized,
                ),
            ):
                result = intelligent_orchestrator.materialize_worker3_market_environment(
                    RUN, lab_rows=rows
                )
            output = Path(result["macro_ticker_context_manifest_path"])
            self.assertTrue(output.is_file())
            self.assertFalse(output.with_suffix(".json.tmp").exists())
            document = json.loads(output.read_text(encoding="utf-8"))
            diagnostics = document["diagnostics"]
            self.assertEqual(document["authority"], "ADVISORY_ONLY")
            self.assertFalse(document["trading_authority"])
            self.assertEqual(document["source_lab_schema_version"], "lab_signal_book_v4")
            self.assertEqual(diagnostics["macro_ticker_context_requested"], 2)
            self.assertEqual(diagnostics["macro_ticker_context_stale"], 1)
            self.assertEqual(diagnostics["macro_ticker_context_invalid"], 1)
            self.assertTrue(diagnostics["macro_ticker_context_reconciled"])
            self.assertEqual(document["invalid_context_examples"][0]["ticker"], "BAD")
            first_bytes = output.read_bytes()
            with (
                patch.object(intelligent_orchestrator.cfg, "RUNS_DIR", runs),
                patch.object(intelligent_orchestrator.cfg, "MACRO_DIR", root / "macro"),
                patch(
                    "contracts.interpreter_macro_context.materialize_interpreter_macro_context",
                    return_value=materialized,
                ),
            ):
                replay = intelligent_orchestrator.materialize_worker3_market_environment(
                    RUN, lab_rows=rows
                )
            self.assertEqual(output.read_bytes(), first_bytes)
            self.assertEqual(
                replay["macro_ticker_context_manifest_sha256"],
                result["macro_ticker_context_manifest_sha256"],
            )

    def test_supplied_rows_must_match_the_hashed_lab_book(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runs = root / "runs"
            run_dir = runs / RUN
            persisted_rows = [_row("AAA", "CALL")]
            supplied_rows = [_row("BBB", "PUT")]
            (run_dir / "intelligence_lab").mkdir(parents=True)
            (run_dir / "run_meta.json").write_text(json.dumps({
                "dynamic_plan": {"last_completed_session": SESSION},
            }), encoding="utf-8")
            (run_dir / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").write_text(
                json.dumps({
                    "lab_schema_version": "lab_signal_book_v2",
                    "run_id": RUN,
                    "candidate_count": 1,
                    "rows": persisted_rows,
                }),
                encoding="utf-8",
            )
            packet = _packet()
            packet["created_at_utc"] = "2026-09-10T20:00:00Z"
            materialized = {
                "packet": packet,
                "reference": {
                    "packet_id": packet["packet_id"],
                    "path": "interpreter/interpreter_macro_context.json",
                    "sha256": _hash(packet),
                },
            }
            with (
                patch.object(intelligent_orchestrator.cfg, "RUNS_DIR", runs),
                patch.object(intelligent_orchestrator.cfg, "MACRO_DIR", root / "macro"),
                patch(
                    "contracts.interpreter_macro_context.materialize_interpreter_macro_context",
                    return_value=materialized,
                ),
                self.assertRaisesRegex(RuntimeError, "differ from the hashed Lab book"),
            ):
                intelligent_orchestrator.materialize_worker3_market_environment(
                    RUN, lab_rows=supplied_rows
                )


if __name__ == "__main__":
    unittest.main()
