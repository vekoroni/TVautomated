from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.automation_v2.package_publisher import publish_package


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(root: Path, *, corrupt=False) -> Path:
    asset = root / "NFLX_daily.png"
    asset.write_bytes(b"chart")
    lab = root / "NFLX_lab_structured.json"
    lab.write_bytes(b"lab")
    manifest = root / "ticker_evidence_package.json"
    manifest.write_text(json.dumps({
        "schema_version": "automation_v2.evidence_package.1",
        "ticker": "NFLX", "status": "complete", "findings": [],
        "required_kinds": ["daily"],
        "assets": [{
            "kind": "daily", "filename": asset.name,
            "sha256": "bad" if corrupt else digest(asset),
        }],
        "structured_lab": {
            "filename": lab.name, "sha256": digest(lab),
        },
        "published": False,
    }))
    return manifest


class PackagePublisherTests(unittest.TestCase):
    def test_default_is_validation_only(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            result = publish_package(
                manifest_path=package(base),
                charts_directory=base / "charts",
            )
            self.assertEqual(result.status, "validated")
            self.assertFalse((base / "charts" / "NFLX_daily.png").exists())

    def test_publish_requires_feature_flag(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            result = publish_package(
                manifest_path=package(base),
                charts_directory=base / "charts",
                publish_requested=True, feature_enabled=False,
            )
            self.assertEqual(
                result.findings, ("PUBLISH_FEATURE_FLAG_DISABLED",)
            )

    def test_hash_mismatch_stops_before_copy(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            result = publish_package(
                manifest_path=package(base, corrupt=True),
                charts_directory=base / "charts",
                publish_requested=True, feature_enabled=True,
            )
            self.assertIn("PACKAGE_HASH_MISMATCH:daily", result.findings)
            self.assertFalse((base / "charts" / "NFLX_daily.png").exists())

    def test_explicit_enabled_publish_copies_asset(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            result = publish_package(
                manifest_path=package(base),
                charts_directory=base / "charts",
                publish_requested=True, feature_enabled=True,
            )
            self.assertEqual(result.status, "published")
            self.assertTrue((base / "charts" / "NFLX_daily.png").is_file())

    def test_existing_target_is_protected(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            charts = base / "charts"
            charts.mkdir()
            (charts / "NFLX_daily.png").write_bytes(b"existing")
            result = publish_package(
                manifest_path=package(base), charts_directory=charts,
                publish_requested=True, feature_enabled=True,
            )
            self.assertIn(
                "PUBLISH_TARGET_EXISTS:NFLX_daily.png", result.findings
            )
            self.assertEqual(
                (charts / "NFLX_daily.png").read_bytes(), b"existing"
            )


if __name__ == "__main__":
    unittest.main()
