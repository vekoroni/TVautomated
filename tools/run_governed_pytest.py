"""Run the governed AVSHUNTER pytest suite with the production Python.

The production Python 3.14 installation contains the compiled application
dependencies but not pytest. The legacy project venv contains pytest, but its
compiled NumPy/Pandas wheels target Python 3.13. Appending (not prepending) the
venv site-packages lets Python 3.14 retain its own compatible application
packages while importing the pure-Python test runner and plugins.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTEST_SITE = ROOT / "venv" / "Lib" / "site-packages"


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(PYTEST_SITE) not in sys.path:
        sys.path.append(str(PYTEST_SITE))
    import pytest

    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
