from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "avs_fix_002_stage0.py"
DESIGN_PATH = ROOT / "docs" / "AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md"
REQUIREMENT_PATHS = (
    ROOT / "docs" / "requirements" / "AVS-REQ-FIX-002_Annex_A_algorithms_and_models.md",
    ROOT / "docs" / "requirements" / "AVS-REQ-FIX-002_developer_requirements.md",
)


def _load_tool():
    specification = importlib.util.spec_from_file_location("avs_fix_002_stage0", TOOL_PATH)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_design_authority_contains_v12_mandatory_controls() -> None:
    content = DESIGN_PATH.read_text(encoding="utf-8")
    required = (
        "FINAL v1.2",
        "ProviderSessionFinality",
        "contracts_at_budget = floor(desk_budget_amount / contract_cost_at_ask)",
        "MarketRateObservation",
        "Current execution-evidence state",
        "Activity-maturation state",
        "positive out-of-sample Brier Skill Score",
        "Stage 7 — Release, controlled cycle and operational acceptance",
    )
    missing = [value for value in required if value not in content]
    assert not missing, f"v1.2 design controls missing: {missing}"


def test_governing_requirements_are_present_and_aligned_to_v12() -> None:
    tool = _load_tool()
    expected = tuple(path.relative_to(ROOT).as_posix() for path in REQUIREMENT_PATHS)
    assert tool.GOVERNING_REQUIREMENTS == expected
    for path in REQUIREMENT_PATHS:
        content = path.read_text(encoding="utf-8")
        assert "v1.2" in content
        assert "correction record" in content

    annex = REQUIREMENT_PATHS[0].read_text(encoding="utf-8")
    requirements = REQUIREMENT_PATHS[1].read_text(encoding="utf-8")
    assert "Provider completeness is assessed at two distinct grains" in annex
    assert "timedelta.total_seconds()" in requirements
    assert "v1.2 (sole development authority)" in requirements


def test_production_entrypoint_import_graph_has_no_untracked_dependency() -> None:
    tool = _load_tool()
    graph = tool.import_graph(ROOT, tool.DEFAULT_ENTRYPOINTS)
    assert graph["missing_entrypoints"] == []
    assert graph["untracked_reachable_dependencies"] == []
    assert graph["node_count"] > 0
    assert graph["passed"] is True


def test_sqlite_snapshot_is_integral_and_restorable(tmp_path: Path) -> None:
    tool = _load_tool()
    source = tmp_path / "source.sqlite"
    connection = sqlite3.connect(source)
    try:
        connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO evidence(value) VALUES(?)",
            [("one",), ("two",), ("three",)],
        )
        connection.commit()
    finally:
        connection.close()

    result = tool.snapshot_database(source, tmp_path / "backup" / "source.sqlite")

    assert result["source_integrity"] == "ok"
    assert result["snapshot_integrity"] == "ok"
    assert result["table_counts_match_source"] is True
    assert result["isolated_restore_verified"] is True
