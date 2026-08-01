"""
Runs the real Intelligence Lab export-mapper JS tests (tests/js/) as part of
the unified pytest suite. These tests eval the ACTUAL inline <script> from
intelligence-lab/static/index.html (see tests/js/lab_export_harness.js) rather
than a Python reimplementation, so a regression in the real export code is
caught here even though the test runner is pytest.

Requires Node.js on PATH. If Node is unavailable, the test is skipped rather
than failed, since Node is an external tool dependency, not a Python package.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
JS_DIR = ROOT / "js"

JS_TESTS = sorted(JS_DIR.glob("test_*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available on PATH")
@pytest.mark.parametrize("js_test", JS_TESTS, ids=[p.name for p in JS_TESTS])
def test_js_export_mapper(js_test):
    result = subprocess.run(
        ["node", str(js_test)],
        cwd=str(JS_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{js_test.name} failed (exit {result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
