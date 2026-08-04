import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline_interpreter.automation_v2.lab_batch import run_lab_batch


class LabBatchTests(unittest.TestCase):
    def source(self, root):
        path = root / "avshunter_signals_run1.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "Run_ID", "Ticker", "Priority_Rank", "Verdict", "RR", "EV"
            ])
            writer.writeheader()
            writer.writerows([
                {"Run_ID": "run1", "Ticker": "GOOD", "Priority_Rank": "2",
                 "Verdict": "GO", "RR": "2", "EV": "0.2"},
                {"Run_ID": "run1", "Ticker": "BAD", "Priority_Rank": "1",
                 "Verdict": "GO", "RR": "-1", "EV": "0.2"},
                {"Run_ID": "run1", "Ticker": "BLOCK", "Priority_Rank": "3",
                 "Verdict": "CONTRACT_REPAIR", "RR": "3", "EV": "0.2"},
                {"Run_ID": "run1", "Ticker": "NOEV", "Priority_Rank": "4",
                 "Verdict": "GO", "RR": "3", "EV": "0"},
            ])
        return path

    def test_plan_uses_lab_and_stops_negative_rr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            outputs.mkdir()
            self.source(outputs)
            state_path = run_lab_batch(
                pipeline_outputs=outputs, staging_root=root / "staging",
                output_directory=root / "batch", invocation_id="b1",
            )
            state = json.loads(state_path.read_text())
            self.assertEqual(["GOOD"], [x["ticker"] for x in state["candidates"]])
            bad = next(x for x in state["stopped"] if x["ticker"] == "BAD")
            self.assertEqual(["NEGATIVE_RR"], bad["veto_codes"])
            self.assertEqual("STOP", bad["effective_verdict"])
            noev = next(x for x in state["stopped"] if x["ticker"] == "NOEV")
            self.assertIn("NON_POSITIVE_EV", noev["veto_codes"])

    def test_shadow_dispatch_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            outputs.mkdir()
            self.source(outputs)
            with patch(
                "pipeline_interpreter.automation_v2.lab_batch.run_e2e_workflow",
                side_effect=RuntimeError("MISSING_EVIDENCE"),
            ):
                state_path = run_lab_batch(
                    pipeline_outputs=outputs, staging_root=root / "staging",
                    output_directory=root / "batch", invocation_id="b1",
                    execute_shadow=True,
                )
            state = json.loads(state_path.read_text())
            self.assertEqual("incomplete", state["status"])
            self.assertEqual("STOP", state["steps"]["GOOD"]["effective_verdict"])

    def test_capture_runner_precedes_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            outputs.mkdir()
            self.source(outputs)
            calls = []
            provider = object()

            def capture(ticker, ticker_root):
                calls.append(("capture", ticker, ticker_root.name))

            def interpret(**kwargs):
                calls.append(("interpret", kwargs["ticker"], kwargs["staging_root"].name))
                self.assertIs(kwargs["shadow_provider"], provider)
                output = kwargs["output_directory"]
                output.mkdir(parents=True)
                state = output / "workflow_state.json"
                state.write_text(json.dumps({
                    "status": "passed", "go_no_go": "SHADOW_PASSED_NOT_PRODUCTION_AUTHORIZED",
                    "steps": {"shadow_ingestion": {"effective_verdict": "STOP"}},
                }))
                return state

            with patch(
                "pipeline_interpreter.automation_v2.lab_batch.run_e2e_workflow",
                side_effect=interpret,
            ):
                state_path = run_lab_batch(
                    pipeline_outputs=outputs,
                    staging_root=root / "staging",
                    output_directory=root / "batch",
                    invocation_id="b1",
                    execute_shadow=True,
                    capture_runner=capture,
                    shadow_provider=provider,
                )
            state = json.loads(state_path.read_text())
            self.assertEqual("passed", state["status"])
            self.assertEqual(["capture", "interpret"], [item[0] for item in calls])


if __name__ == "__main__":
    unittest.main()
