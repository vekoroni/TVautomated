from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.package_shadow import run_package_shadow


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageShadowTests(unittest.TestCase):
    def test_shadow_publication_and_stateless_veto_preservation(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            chart = base / "NFLX_daily.png"
            chart.write_bytes(b"chart")
            lab = base / "NFLX_lab_structured.json"
            lab.write_text(json.dumps({
                "schema_version": "automation_v2.lab_structured.1",
                "ticker": "NFLX", "run_id": "run-1", "status": "staged",
                "sections": {"trade_setup": {"rr_predicted": "-0.5"}},
                "sovereign": {
                    "rr": "-0.5",
                    "veto_codes": [
                        "NEGATIVE_RR", "LIVE_CONFIRMATION_REQUIRED"
                    ],
                },
            }))
            manifest = base / "ticker_evidence_package.json"
            manifest.write_text(json.dumps({
                "schema_version": "automation_v2.evidence_package.1",
                "ticker": "NFLX", "status": "complete", "findings": [],
                "required_kinds": ["daily"],
                "assets": [{
                    "kind": "daily", "filename": chart.name,
                    "sha256": sha(chart),
                }],
                "structured_lab": {
                    "filename": lab.name, "sha256": sha(lab),
                },
            }))
            report_path = run_package_shadow(
                manifest_path=manifest,
                output_directory=base / "shadow",
                invocation_id="inv-1",
            )
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], "passed")
            self.assertTrue(report["sovereign_preserved"])
            self.assertIn("NEGATIVE_RR", report["actual_sovereign_vetoes"])
            self.assertEqual(report["effective_verdict"], "STOP")
            self.assertEqual(report["eil_action"], "STOP")
            self.assertFalse(report["production_charts_touched"])
            self.assertFalse(report["published"])
            self.assertTrue(
                (base / "shadow" / "shadow_charts" / "NFLX_daily.png").is_file()
            )


if __name__ == "__main__":
    unittest.main()
