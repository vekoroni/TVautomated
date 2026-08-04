import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.production_deploy import deploy_package


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionDeployTests(unittest.TestCase):
    def package(self, root):
        pkg = root / "package"
        pkg.mkdir()
        asset = pkg / "NFLX_daily.png"
        asset.write_bytes(b"new")
        lab = pkg / "NFLX_lab_structured.json"
        lab.write_text("{}", encoding="utf-8")
        manifest = pkg / "ticker_evidence_package.json"
        manifest.write_text(json.dumps({
            "schema_version": "automation_v2.evidence_package.1",
            "status": "complete", "findings": [], "ticker": "NFLX",
            "required_kinds": ["daily"],
            "assets": [{"kind": "daily", "filename": asset.name, "sha256": sha(asset)}],
            "structured_lab": {"filename": lab.name, "sha256": sha(lab)},
        }), encoding="utf-8")
        return manifest

    def test_requires_both_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = deploy_package(
                manifest_path=self.package(root), charts_directory=root / "charts",
                backup_directory=root / "backup", deployment_id="d1",
                confirmed=False, feature_enabled=True,
            )
            self.assertEqual("stopped", result["status"])

    def test_backs_up_replaces_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.package(root)
            charts = root / "charts"
            charts.mkdir()
            (charts / "NFLX_daily.png").write_bytes(b"old")
            backup = root / "backup"
            result = deploy_package(
                manifest_path=manifest, charts_directory=charts,
                backup_directory=backup, deployment_id="d1",
                confirmed=True, feature_enabled=True,
            )
            self.assertEqual("published", result["status"])
            self.assertEqual(b"new", (charts / "NFLX_daily.png").read_bytes())
            self.assertEqual(b"old", (backup / "NFLX_daily.png").read_bytes())
            receipt = json.loads((backup / "production_deployment_receipt.json").read_text())
            self.assertTrue(receipt["verified"])


if __name__ == "__main__":
    unittest.main()
