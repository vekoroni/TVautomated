"""Inspect or retry governed canonical-data projections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_data.phantom_option_projection import deliver_phantom_option_events
from canonical_data.projection_outbox import ProjectionOutbox


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/canonical/control_plane.sqlite"),
    )
    parser.add_argument(
        "--phantom",
        type=Path,
        default=Path("data/phantom/phantom_history.db"),
    )
    parser.add_argument("--deliver", action="store_true")
    parser.add_argument("--limit", type=int, default=100_000)
    args = parser.parse_args()
    outbox = ProjectionOutbox(args.registry)
    delivered = ()
    if args.deliver:
        delivered = deliver_phantom_option_events(
            registry_path=args.registry,
            phantom_database_path=args.phantom,
            limit=args.limit,
        )
    report = {
        "contract_version": "data-projection-reconciliation-v1",
        "delivered": len(delivered),
        "health": outbox.health_summary(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    counts = report["health"]["counts"]
    return 1 if counts["PROCESSING"] or counts["FAILED_RETRYABLE"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
