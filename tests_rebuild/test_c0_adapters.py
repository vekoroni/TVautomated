"""P0-3 adapters: git facts (temporary repositories), legacy plan parsing, shell parity."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from avshunter.c0_run.adapters import legacy
from avshunter.c0_run.adapters.git import collect_git_facts, untracked_imported_modules

REPO = Path(__file__).resolve().parents[1]
PATHS = ["./*.py", "worker3/", "scripts/"]

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "worker3").mkdir()
    (tmp_path / "main_entry.py").write_text("import json\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


@needs_git
def test_clean_repository(repo):
    facts = collect_git_facts(repo, PATHS)
    assert facts.clean_tree and facts.release_id is None and not facts.untracked_imported_modules


@needs_git
def test_modified_file_and_release_tag(repo):
    _git(repo, "tag", "rel-20260917-1")
    assert collect_git_facts(repo, PATHS).release_id == "rel-20260917-1"
    (repo / "main_entry.py").write_text("import os\n", encoding="utf-8")
    facts = collect_git_facts(repo, PATHS)
    assert not facts.clean_tree and facts.modified_tracked_files


@needs_git
def test_untracked_import_is_detected(repo):
    (repo / "main_entry.py").write_text("from worker3.lab_contract import X\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "use contract")
    (repo / "worker3" / "lab_contract.py").write_text("X = 1\n", encoding="utf-8")
    facts = collect_git_facts(repo, PATHS)
    assert "worker3/lab_contract.py" in facts.untracked_production_files
    assert facts.untracked_imported_modules and "worker3.lab_contract" in facts.untracked_imported_modules[0]


@needs_git
def test_untracked_data_outside_production_paths_is_ignored(repo):
    (repo / "data").mkdir()
    (repo / "data" / "output.csv").write_text("a\n", encoding="utf-8")
    assert collect_git_facts(repo, PATHS).clean_tree


def test_bare_name_match_suppressed_when_tracked_module_exists():
    tracked = ["scripts/utils.py", "main_entry.py"]
    assert untracked_imported_modules(REPO, tracked, ["worker3/utils.py"], PATHS) == ()


def test_plan_json_parsing_and_thesis_session():
    output = "2026-09-17 INFO starting\n{\n  \"existing_thesis_id\": \"book:20260916_223756:2026-09-16:0928\",\n  \"last_completed_session\": \"2026-09-16\",\n  \"nested\": {\"a\": 1}\n}\n"
    plan = legacy._last_json_object(output)
    assert plan["last_completed_session"] == "2026-09-16"
    assert legacy.thesis_session_from_id(plan["existing_thesis_id"]) == date(2026, 9, 16)
    assert legacy.thesis_session_from_id(None) is None
    with pytest.raises(ValueError):
        legacy._last_json_object("no plan here")


def test_child_environment_overrides_shell_with_configuration():
    env = legacy.child_environment({"AVSHUNTER_CDS2_OHLCV_MODE": "OFF", "PATH": "p"},
                                   {"AVSHUNTER_CDS2_OHLCV_MODE": "ACTIVE"}, {"AVSHUNTER_RUN_CONTEXT_ID": "id"})
    assert env["AVSHUNTER_CDS2_OHLCV_MODE"] == "ACTIVE" and env["PATH"] == "p" and env["AVSHUNTER_RUN_CONTEXT_ID"] == "id"


def test_launcher_resolves_flags_from_configuration_in_clean_shell():
    """A plain shell with no AVSHUNTER_* variables gets the configured legacy flags."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AVSHUNTER_")}
    code = (
        "from datetime import date\n"
        "from avshunter.config.adapters import load_registry\n"
        "from avshunter.c0_run.context import resolve_legacy_flags\n"
        "import json\n"
        "print(json.dumps(resolve_legacy_flags(load_registry().resolve(date(2026, 9, 17)))))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, check=True)
    flags = json.loads(result.stdout.strip().splitlines()[-1])
    assert flags["AVSHUNTER_CANONICAL_DATA_ENABLED"] == "1"
    assert flags["AVSHUNTER_CDS2_OHLCV_MODE"] == "ACTIVE"
