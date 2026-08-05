from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vanguard.layer2_statistical import actuarial_query


REPO_ROOT = Path(__file__).resolve().parents[1]
VANGUARD_DATA = Path(r"C:\Users\ACKVerissimo\vanguard\data")
V7_DB = VANGUARD_DATA / "actuarial_database_v7.parquet"
V7_CACHE = VANGUARD_DATA / "actuarial_cache_v7.parquet"


def _class_assignments(path: Path, class_name: str) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    target = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    values: dict[str, str] = {}
    for node in target.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        if isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = ast.unparse(node.value)
    return values


class ActuarialV7CutoverPathTests(unittest.TestCase):
    def test_registry_and_live_receipts_identify_v7(self) -> None:
        registry = json.loads((REPO_ROOT / "config" / "actuarial_registry.json").read_text())
        status = json.loads((VANGUARD_DATA / "pipeline_status.json").read_text())
        last_run = json.loads((VANGUARD_DATA / "actuarial_last_run.json").read_text())
        transition = json.loads(
            (VANGUARD_DATA / "transition_matrix" / "transition_matrix_meta_latest.json").read_text()
        )

        self.assertEqual(Path(registry["canonical_database"]["path"]), V7_DB)
        self.assertEqual(Path(registry["canonical_cache"]["path"]), V7_CACHE)
        self.assertEqual(Path(status["actuarial_db_path"]), V7_DB)
        self.assertEqual(Path(last_run["actuarial_db_path"]), V7_DB)
        self.assertEqual(Path(transition["source_actuarial_database"]), V7_DB)
        self.assertEqual(status["schema_version"], "actuarial_v7")
        self.assertEqual(last_run["schema_version"], "actuarial_v7")

    def test_orchestrator_constants_are_v7(self) -> None:
        constants = _class_assignments(
            REPO_ROOT / "intelligent_orchestrator.py", "OrchestratorConfig"
        )
        self.assertIn("actuarial_cache_v7.parquet", constants["ACTUARIAL_CACHE_PATH"])
        self.assertIn("actuarial_database_v7.parquet", constants["ACTUARIAL_DB_PATH"])

    def test_missing_v7_does_not_silently_fall_back_to_v6(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp_dir = Path(directory)
            missing = temp_dir / "actuarial_database.parquet"
            (temp_dir / "actuarial_database_v6.parquet").touch()
            with mock.patch.object(
                actuarial_query, "ACTUARIAL_DATABASE_PATH", str(missing)
            ):
                with self.assertRaisesRegex(FileNotFoundError, str(missing).replace("\\", r"\\")):
                    actuarial_query.ActuarialQueryEngine()

    def test_live_v7_artifacts_exist_and_old_cache_is_not_configured(self) -> None:
        self.assertTrue(V7_DB.is_file() and V7_DB.stat().st_size > 0)
        self.assertTrue(V7_CACHE.is_file() and V7_CACHE.stat().st_size > 0)
        source = (REPO_ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
        executable_source = source[source.index("class OrchestratorConfig"):]
        self.assertNotIn(
            'ACTUARIAL_CACHE_PATH    = VANGUARD_DIR / "data" / "actuarial_cache.parquet"',
            executable_source,
        )
        self.assertNotIn(
            'ACTUARIAL_DB_PATH       = VANGUARD_DIR / "data" / "actuarial_database_v6.parquet"',
            executable_source,
        )


if __name__ == "__main__":
    unittest.main()
