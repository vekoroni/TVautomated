"""Static purity rules for the rebuild package (P0-2 §3.7, P0-3 §3.5)."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "avshunter"

WALL_CLOCK_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("time", "time")}
CLOCK_ALLOWED_FILES = {"c0_run/adapters/clock.py"}
ALLOWED_LITERALS = {0, 1, -1}
LITERAL_SCAN_EXEMPT = {"shared/xnys_calendar.py"}  # calendar arithmetic, provenance-copied


def _python_files():
    return sorted(p for p in PACKAGE.rglob("*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


def test_no_wall_clock_in_rebuild_package():
    offenders = []
    for path in _python_files():
        if _relative(path) in CLOCK_ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", None)
                if (name, node.func.attr) in WALL_CLOCK_CALLS:
                    offenders.append(f"{_relative(path)}:{node.lineno}")
    assert not offenders, f"wall-clock calls outside the clock adapter: {offenders}"


def test_no_numeric_threshold_literals_in_comparisons():
    offenders = []
    for path in _python_files():
        if _relative(path) in LITERAL_SCAN_EXEMPT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for operand in [node.left, *node.comparators]:
                value = None
                if isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float)) and not isinstance(operand.value, bool):
                    value = operand.value
                elif (isinstance(operand, ast.UnaryOp) and isinstance(operand.op, ast.USub)
                      and isinstance(operand.operand, ast.Constant)
                      and isinstance(operand.operand.value, (int, float))):
                    value = -operand.operand.value
                if value is not None and value not in ALLOWED_LITERALS:
                    offenders.append(f"{_relative(path)}:{node.lineno} literal {value}")
    assert not offenders, f"thresholds must come from configuration: {offenders}"


def test_no_sys_path_manipulation():
    offenders = [
        _relative(path)
        for path in _python_files()
        if "sys.path" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"use package imports, not sys.path: {offenders}"


def test_condition_labels_are_not_imported_by_decision_code():
    """P0-8 §6a guard: conditions are analysis dimensions; only the outcome scorer may import them."""
    offenders = []
    for path in _python_files():
        relative = _relative(path)
        if relative.startswith("c12_outcome/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if any("c12_outcome" in name for name in names):
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, f"outcome scoring / condition labels imported outside C12: {offenders}"
