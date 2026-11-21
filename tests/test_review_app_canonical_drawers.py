"""Current review cards retain canonical evidence after Interpreter retirement."""
from pathlib import Path
import shutil
import subprocess
import pytest

@pytest.mark.skipif(shutil.which("node") is None, reason="Node is required for frontend verification")
def test_current_review_canonical_drawers():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "--test", str(root / "tests/js/test_review_app_canonical_drawers.js")],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
