from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.automation_v2.evidence_package import (
    REQUIRED_KINDS,
    assemble_evidence_package,
)


class EvidencePackageTests(unittest.TestCase):
    def _asset(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (20, 20), "blue").save(path)

    def test_complete_package_has_canonical_assets_and_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            run = base / "run"
            run.mkdir()
            assets = []
            for kind in REQUIRED_KINDS:
                path = run / f"NFLX_{kind}.png"
                self._asset(path)
                assets.append({
                    "kind": kind, "filename": path.name,
                })
            # Use a pre-assembled manifest to exercise exact canonical inputs.
            for kind in ("daily", "4h", "1h", "15m", "5m"):
                pass
            # Build discoverable source manifests.
            (run / "timeframe_capture_manifest.json").write_text(json.dumps({
                "schema_version": "capture_v1.timeframe_capture.1",
                "ticker": "NFLX", "status": "captured",
                "assets": [f"NFLX_{k}.png" for k in ("daily","4h","1h","15m","5m")],
            }))
            for screen, kind in {
                "options": "options_chain", "tape": "tape",
                "orderbook": "orderbook", "short": "short",
                "greeks": "options_chain_greeks",
            }.items():
                (run / f"{screen}.json").write_text(json.dumps({
                    "schema_version": "capture_v1.ticker_market_screen.1",
                    "ticker": "NFLX", "screen": screen, "status": "mapped",
                    "assets": [{"filename": f"NFLX_{kind}.png"}],
                }))
            (run / "noii.json").write_text(json.dumps({
                "schema_version": "capture_v1.noii_cross.1",
                "ticker": "NFLX", "status": "captured",
                "assets": [
                    {"phase": "open", "filename": "NFLX_orderbook_imbalance_open.png"},
                    {"phase": "close", "filename": "NFLX_orderbook_imbalance_close.png"},
                ],
            }))
            (run / "lab.json").write_text(json.dumps({
                "schema_version": "automation_v2.lab_structured.1",
                "ticker": "NFLX", "status": "staged",
            }))
            manifest, findings = assemble_evidence_package(
                ticker="NFLX", staging_root=base,
                output_directory=base / "package",
            )
            self.assertEqual(findings, ())
            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["status"], "complete")
            self.assertTrue(all(item["sha256"] for item in payload["assets"]))
            self.assertFalse(payload["published"])

    def test_missing_assets_are_reported(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            manifest, findings = assemble_evidence_package(
                ticker="NFLX", staging_root=base,
                output_directory=base / "package",
            )
            self.assertIn("MISSING_ASSET:daily", findings)
            payload = json.loads(manifest.read_text())
            self.assertEqual(payload["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
