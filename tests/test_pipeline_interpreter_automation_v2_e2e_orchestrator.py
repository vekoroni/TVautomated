from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline_interpreter.automation_v2.e2e_orchestrator import run_e2e_workflow
from pipeline_interpreter.automation_v2.lab_structured import LabStructuredResult


class E2EOrchestratorTests(unittest.TestCase):
    def test_checkpointed_workflow_resumes_without_repeating_steps(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "ticker"
            staging.mkdir()
            output = staging / "workflow"

            def lab(**kwargs):
                target = kwargs["output_file"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("{}")
                return LabStructuredResult(target, "NFLX", "run-1", ())

            def package(**kwargs):
                target = kwargs["output_directory"]
                target.mkdir()
                manifest = target / "ticker_evidence_package.json"
                manifest.write_text("{}")
                return manifest, ()

            def shadow(**kwargs):
                target = kwargs["output_directory"]
                target.mkdir()
                report = target / "package_shadow_report.json"
                report.write_text(json.dumps({
                    "status": "passed", "sovereign_preserved": True,
                    "production_charts_touched": False,
                    "effective_verdict": "STOP",
                }))
                return report

            with (
                patch(
                    "pipeline_interpreter.automation_v2.e2e_orchestrator."
                    "build_structured_lab_manifest", side_effect=lab
                ) as lab_mock,
                patch(
                    "pipeline_interpreter.automation_v2.e2e_orchestrator."
                    "assemble_evidence_package", side_effect=package
                ) as package_mock,
                patch(
                    "pipeline_interpreter.automation_v2.e2e_orchestrator."
                    "validate_package", return_value=({}, ())
                ),
                patch(
                    "pipeline_interpreter.automation_v2.e2e_orchestrator."
                    "run_package_shadow", side_effect=shadow
                ) as shadow_mock,
            ):
                first = run_e2e_workflow(
                    ticker="NFLX", staging_root=staging,
                    pipeline_outputs=base, output_directory=output,
                    invocation_id="inv-1",
                )
                second = run_e2e_workflow(
                    ticker="NFLX", staging_root=staging,
                    pipeline_outputs=base, output_directory=output,
                    invocation_id="inv-1",
                )
            self.assertEqual(first, second)
            self.assertEqual(lab_mock.call_count, 1)
            self.assertEqual(package_mock.call_count, 1)
            self.assertEqual(shadow_mock.call_count, 1)
            state = json.loads(first.read_text())
            self.assertEqual(state["status"], "passed")
            self.assertEqual(
                state["go_no_go"],
                "SHADOW_PASSED_NOT_PRODUCTION_AUTHORIZED",
            )
            self.assertFalse(state["published"])

    def test_output_must_remain_inside_staging(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "ticker"
            staging.mkdir()
            with self.assertRaisesRegex(
                ValueError, "E2E_OUTPUT_MUST_BE_INSIDE"
            ):
                run_e2e_workflow(
                    ticker="NFLX", staging_root=staging,
                    pipeline_outputs=base,
                    output_directory=base / "outside",
                    invocation_id="inv-1",
                )


if __name__ == "__main__":
    unittest.main()
