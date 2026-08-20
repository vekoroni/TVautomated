#!/usr/bin/env python3
"""
Compatibility shim for the production Options Intelligence engine.

The production implementation lives at:
    scripts/avshunter_options_intelligence.py

The old root-level implementation was decommissioned on 2026-05-12 because it
was stale and could be run accidentally. Keep this wrapper so manual commands
or imports resolve to the same engine the orchestrator uses.
"""

from __future__ import annotations

import runpy
from pathlib import Path


PRODUCTION_SCRIPT = Path(__file__).resolve().parent / "scripts" / "avshunter_options_intelligence.py"


def _load_exports() -> None:
    namespace = runpy.run_path(str(PRODUCTION_SCRIPT), run_name="avshunter_options_intelligence")
    globals().update(
        {
            name: value
            for name, value in namespace.items()
            if not (name.startswith("__") and name.endswith("__"))
        }
    )


if __name__ == "__main__":
    runpy.run_path(str(PRODUCTION_SCRIPT), run_name="__main__")
else:
    _load_exports()
