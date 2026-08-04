from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.lab_structured import (
    build_structured_lab_manifest,
)


def write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class StructuredLabTests(unittest.TestCase):
    def test_triage_precedence_and_negative_rr_veto(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            write_csv(base / "lab_triage_view_20260726_120000.csv", [{
                "run_id": "20260726_120000", "ticker": "NFLX",
                "lab_verdict": "READY_EXECUTE", "direction": "PUT",
                "rr_predicted": "-0.4", "call_wall": "75",
                "wbs": "72.1", "expected_move_5d": "6.3",
            }])
            write_csv(base / "eil_enriched_20260726_120000.csv", [{
                "ticker": "NFLX", "lab_verdict": "STALE_VALUE",
                "put_wall": "65", "contract_delta": "-0.4",
            }])
            result = build_structured_lab_manifest(
                ticker="NFLX", pipeline_outputs=base,
                output_file=base / "staged.json",
            )
            payload = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["sections"]["overview"]["lab_verdict"],
                "READY_EXECUTE",
            )
            self.assertEqual(payload["sections"]["options"]["put_wall"], "65")
            self.assertIn("NEGATIVE_RR", payload["sovereign"]["veto_codes"])
            self.assertEqual(payload["sovereign"]["effective_verdict"], "STOP")
            self.assertEqual(payload["sovereign"]["eil_action"], "STOP")
            self.assertFalse(payload["published"])

    def test_exact_ticker_required(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            write_csv(base / "lab_triage_view_20260726_120000.csv", [{
                "run_id": "run", "ticker": "NFLX", "lab_verdict": "WAIT",
            }])
            with self.assertRaisesRegex(LookupError, "LAB_TICKER_NOT_FOUND:F"):
                build_structured_lab_manifest(
                    ticker="F", pipeline_outputs=base,
                    output_file=base / "staged.json",
                )


if __name__ == "__main__":
    unittest.main()
