"""Versioned BEH-001 configuration; an incomplete policy fails closed."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "beh001_behaviour_v1.json"
REQUIRED = ("atr_bars", "swing_reversal_atr", "acceptance", "sot_tolerance", "repair",
            "events", "range", "compression", "maturity", "timeframes")


def load_policy(path: Path | str | None = None) -> Mapping[str, Any]:
    policy = json.loads(Path(path or POLICY_PATH).read_text(encoding="utf-8"))
    if policy.get("version") != "beh001_behaviour_v1":
        raise ValueError("Unsupported BEH-001 policy version")
    missing = [key for key in REQUIRED if policy.get(key) in (None, {}, [])]
    if missing:
        raise ValueError(f"BEH-001 policy missing {missing}")
    return policy
