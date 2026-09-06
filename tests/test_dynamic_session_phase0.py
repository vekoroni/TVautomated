from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from canonical_data.session_clock import SessionState
from contracts.dynamic_session_contract import (
    DataExceptionReason,
    DynamicSessionFeatureFlags,
    EvidenceOrigin,
    EvidenceState,
    FEATURE_FLAG_ENV_VARS,
    OperationalContext,
    ProfileCadence,
    ProfileLifecycleState,
)
from scripts.release_baseline import (
    finalise,
    repository_source_inventory,
    source_snapshot_coverage,
    sqlite_snapshot,
    verify_backup,
)


REPO = Path(__file__).resolve().parents[1]
AUTHORITY_MANIFEST = REPO / "contracts" / "dynamic_session_authority_v1.json"


class DynamicSessionContractTests(unittest.TestCase):
    def test_shared_exchange_clock_has_required_states(self) -> None:
        self.assertEqual(
            {item.value for item in SessionState},
            {"CLOSED", "PREMARKET", "REGULAR", "AFTER_HOURS"},
        )

    def test_phase0_vocabulary_is_complete_and_nonempty(self) -> None:
        for enum_type in (
            OperationalContext,
            EvidenceState,
            ProfileLifecycleState,
            ProfileCadence,
            EvidenceOrigin,
            DataExceptionReason,
        ):
            values = [item.value for item in enum_type]
            self.assertTrue(values)
            self.assertEqual(len(values), len(set(values)))

    def test_all_new_features_are_disabled_by_default(self) -> None:
        flags = DynamicSessionFeatureFlags.from_environment({})
        self.assertFalse(any(getattr(flags, field) for field in flags.__slots__))
        self.assertEqual(len(FEATURE_FLAG_ENV_VARS), 9)

    def test_feature_flags_are_independently_reversible(self) -> None:
        for environment_name in FEATURE_FLAG_ENV_VARS:
            flags = DynamicSessionFeatureFlags.from_environment(
                {environment_name: "true"}
            )
            self.assertEqual(
                sum(bool(getattr(flags, field)) for field in flags.__slots__), 1
            )

    def test_authority_manifest_has_one_capital_owner(self) -> None:
        manifest = json.loads(AUTHORITY_MANIFEST.read_text(encoding="utf-8"))
        fields = manifest["fields"]
        self.assertEqual(len(fields), len({field["name"] for field in fields}))
        capital_fields = [field for field in fields if field["authority"] == "capital"]
        self.assertTrue(capital_fields)
        self.assertEqual({field["owner"] for field in capital_fields}, {"execution_gate"})
        for advisory in ("macro_context", "ev3_state", "risk_reward_display"):
            field = next(item for item in fields if item["name"] == advisory)
            self.assertEqual(field["authority"], "advisory_only")

    def test_authority_manifest_flags_match_code(self) -> None:
        manifest = json.loads(AUTHORITY_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["feature_flags"]), set(FEATURE_FLAG_ENV_VARS))
        self.assertFalse(any(manifest["feature_flags"].values()))


class ReleaseBaselineTests(unittest.TestCase):
    def test_repository_inventory_cannot_omit_core_packages_or_launchers(self) -> None:
        inventory = repository_source_inventory(REPO)
        for required in (
            "orchestrator/dynamic_dispatcher.py",
            "market_structure/profile.py",
            "run_evening.bat",
            "run_premarket.bat",
        ):
            self.assertIn(required, inventory)
        self.assertFalse(any("/venv/" in f"/{path}/" for path in inventory))

    def test_source_coverage_fails_when_repository_source_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            source = backup / "source_rebuildable"
            (source / "orchestrator").mkdir(parents=True)
            (source / "orchestrator" / "dynamic_dispatcher.py").write_text(
                "# captured\n", encoding="utf-8"
            )
            expected = {
                "orchestrator/dynamic_dispatcher.py",
                "market_structure/profile.py",
            }
            with patch(
                "scripts.release_baseline.repository_source_inventory",
                return_value=expected,
            ):
                coverage = source_snapshot_coverage(backup, REPO)
            self.assertFalse(coverage["passed"])
            self.assertEqual(coverage["missing"], ["market_structure/profile.py"])

    def test_source_coverage_requires_a_matching_hash_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            source = backup / "source_full_prechange"
            source.mkdir()
            captured = source / "run_evening.bat"
            captured.write_text("@echo off\n", encoding="utf-8")
            (backup / "source_full_prechange_manifest.json").write_text(
                json.dumps([{
                    "relative_path": "run_evening.bat",
                    "sha256": "0" * 64,
                }]),
                encoding="utf-8",
            )
            with patch(
                "scripts.release_baseline.repository_source_inventory",
                return_value={"run_evening.bat"},
            ):
                coverage = source_snapshot_coverage(backup, REPO)
            self.assertFalse(coverage["passed"])
            self.assertEqual(
                coverage["manifest_hash_failures"], ["run_evening.bat"]
            )

    def test_frozen_inventory_distinguishes_new_release_file_from_omission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            source = backup / "source_full_prechange"
            source.mkdir()
            captured = source / "existing.py"
            captured.write_text("# baseline\n", encoding="utf-8")
            from scripts.release_baseline import sha256_file

            (backup / "source_inventory_prechange.json").write_text(
                json.dumps({"paths": ["existing.py"]}), encoding="utf-8"
            )
            (backup / "source_full_prechange_manifest.json").write_text(
                json.dumps([{
                    "relative_path": "existing.py",
                    "sha256": sha256_file(captured),
                }]),
                encoding="utf-8",
            )
            with patch(
                "scripts.release_baseline.repository_source_inventory",
                return_value={"existing.py", "new_release_file.py"},
            ):
                coverage = source_snapshot_coverage(backup, REPO)
            self.assertTrue(coverage["passed"])
            self.assertEqual(
                coverage["added_after_baseline"], ["new_release_file.py"]
            )

    def test_sqlite_snapshot_and_isolated_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.sqlite"
            connection = sqlite3.connect(source)
            try:
                connection.execute("CREATE TABLE observations(id INTEGER, value TEXT)")
                connection.executemany(
                    "INSERT INTO observations VALUES (?, ?)", [(1, "a"), (2, "b")]
                )
                connection.commit()
            finally:
                connection.close()
            backup = root / "release"
            database_dir = backup / "databases"
            database_dir.mkdir(parents=True)
            snapshot = database_dir / "control_plane.sqlite"
            record = sqlite_snapshot(source, snapshot)
            self.assertEqual(record["integrity_check"], "ok")
            self.assertEqual(record["table_counts"], {"observations": 2})

            manifest = [
                {
                    "relative_path": "databases/control_plane.sqlite",
                    "bytes": snapshot.stat().st_size,
                    "sha256": record["sha256"],
                }
            ]
            (backup / "file_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            verification = verify_backup(backup)
            self.assertTrue(verification["passed"])
            self.assertTrue(verification["isolated_restore_removed_after_verification"])
            self.assertEqual(len(verification["database_results"]), 1)

    def test_release_manifest_takes_precedence_over_raw_capture_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            (backup / "databases").mkdir()
            stable = backup / "stable.txt"
            stable.write_text("stable", encoding="utf-8")
            raw = backup / "changing-runtime-output.txt"
            raw.write_text("before", encoding="utf-8")
            from scripts.release_baseline import sha256_file

            (backup / "file_manifest.json").write_text(
                json.dumps(
                    [
                        {"relative_path": stable.name, "sha256": sha256_file(stable)},
                        {"relative_path": raw.name, "sha256": sha256_file(raw)},
                    ]
                ),
                encoding="utf-8",
            )
            (backup / "release_file_manifest.json").write_text(
                json.dumps(
                    [{"relative_path": stable.name, "sha256": sha256_file(stable)}]
                ),
                encoding="utf-8",
            )
            raw.write_text("after", encoding="utf-8")
            self.assertTrue(verify_backup(backup)["passed"])

    def test_finalise_uses_full_source_manifest_and_ignores_empty_db_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary)
            source = backup / "source_full_prechange"
            source.mkdir()
            captured = source / "run_evening.bat"
            captured.write_text("@echo off\n", encoding="utf-8")
            from scripts.release_baseline import sha256_file

            (backup / "source_full_prechange_manifest.json").write_text(
                json.dumps(
                    [{
                        "relative_path": "run_evening.bat",
                        "bytes": captured.stat().st_size,
                        "sha256": sha256_file(captured),
                    }]
                ),
                encoding="utf-8",
            )
            databases = backup / "databases"
            databases.mkdir()
            (databases / "failed_snapshot.db").write_bytes(b"")
            with patch(
                "scripts.release_baseline.repository_source_inventory",
                return_value={"run_evening.bat"},
            ), patch(
                "scripts.release_baseline.environment_record",
                return_value={
                    "git_head": "TEST", "git_status_lines": [],
                    "acceptance_test_runtime": {"pytest_available": True},
                },
            ):
                result = finalise(backup, REPO)

            release_records = json.loads(
                (backup / "release_file_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                release_records[0]["relative_path"],
                "source_full_prechange/run_evening.bat",
            )
            self.assertTrue(result["restore_verification"]["passed"])
            self.assertEqual(result["databases"], [])
            self.assertEqual(
                result["ignored_zero_byte_database_artifacts"],
                ["databases/failed_snapshot.db"],
            )


if __name__ == "__main__":
    unittest.main()
