"""S0 tests: clean-checkout static imports and explicit release boundaries."""

import importlib.util
from pathlib import Path

from tools.avs_int001_stage0 import (
    DESIGN, ENTRYPOINTS, RESEARCH_ONLY, build_baseline, inspect_static_imports,
)


ROOT = Path(__file__).resolve().parents[1]


def test_untracked_local_import_is_reported_without_importing_code(tmp_path):
    (tmp_path / "app.py").write_text("from domain.helper import value\n", encoding="utf-8")
    package = tmp_path / "domain"
    package.mkdir()
    (package / "helper.py").write_text("value = 1\n", encoding="utf-8")

    result = inspect_static_imports(tmp_path, ("app.py",), {"app.py"})

    assert result["untracked_or_absent_local_imports"] == ["domain/helper.py"]
    assert result["local_import_closure_count"] == 2


def test_tracked_local_import_and_relative_import_are_in_closure(tmp_path):
    package = tmp_path / "feature"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "entry.py").write_text("from .helper import value\n", encoding="utf-8")
    (package / "helper.py").write_text("value = 1\n", encoding="utf-8")
    tracked = {"feature/entry.py", "feature/helper.py"}

    result = inspect_static_imports(tmp_path, ("feature/entry.py",), tracked)

    assert result["untracked_or_absent_local_imports"] == []
    assert result["local_import_closure_count"] == 2


def test_named_production_imports_are_in_the_git_index():
    baseline = build_baseline(ROOT)
    closure = baseline["production_static_imports"]
    assert closure["entrypoints"] == list(ENTRYPOINTS)
    assert closure["untracked_or_absent_local_imports"] == []
    assert closure["parse_errors"] == {}


def test_war_v2_is_not_mistaken_for_the_live_v1_route():
    baseline = build_baseline(ROOT)
    assert "pipeline_interpreter/war_view.py" in ENTRYPOINTS
    assert set(baseline["research_only_files"]) == set(RESEARCH_ONLY)
    # Local research code can be present without being a governed live import.
    assert all(value in {"TRACKED", "LOCAL_UNTRACKED", "ABSENT"}
               for value in baseline["research_only_files"].values())


def test_design_status_is_recorded_not_inferred_from_file_presence():
    baseline = build_baseline(ROOT)
    assert DESIGN == "docs/AVS-SD-INT-001_DECISION_GRADE_PIPELINE_INTEGRATION.md"
    assert isinstance(baseline["design_tracked"], bool)
    assert isinstance(baseline["tags_at_head"], list)


def test_real_lab_app_mounts_the_saved_war_routes_without_starting_server():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_int001_mount_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes = {rule.rule for rule in module.app.url_map.iter_rules()}
    assert "/api/interpreter/war" in routes
    assert "/api/interpreter/war/<run_id>/<ticker>/<report_id>.html" in routes
