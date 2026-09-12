"""Build a read-only Stage 6 learning snapshot from canonical evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger
from canonical_data.outcome_learning import (
    build_outcome_learning_snapshot,
    learning_policy_from_config,
    write_outcome_learning_snapshot,
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ledger",
        type=Path,
        default=ROOT / "data" / "canonical" / "decision_outcome_ledger.sqlite",
    )
    parser.add_argument(
        "--control-plane",
        type=Path,
        default=ROOT / "data" / "canonical" / "control_plane.sqlite",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "governed_constants_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    snapshot = build_outcome_learning_snapshot(
        DecisionOutcomeLedger(arguments.ledger, read_only=True),
        policy=learning_policy_from_config(arguments.config),
        control_plane_path=arguments.control_plane,
    )
    write_outcome_learning_snapshot(arguments.output, snapshot)
    print(json.dumps({
        "output": str(arguments.output),
        "summary": snapshot["summary"],
        "model_activation": snapshot["model_activation"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
