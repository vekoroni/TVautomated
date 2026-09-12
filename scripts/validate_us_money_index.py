#!/usr/bin/env python3
"""Validate and normalise an advisory US Money Index sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.us_money_index_contract import load_us_money_index_sidecar  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=str(ROOT / "dropbox" / "macro" / "avshunter_us_money_index.json"),
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        packet = load_us_money_index_sidecar(args.input)
    except Exception as error:
        print(f"US MONEY INDEX INVALID: {error}", file=sys.stderr)
        return 2
    if args.output:
        Path(args.output).write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": "VALID_ADVISORY",
        "packet_id": packet["packet_id"],
        "source_contract_version": packet["source_contract_version"],
        "normalised_contract_version": packet["contract_version"],
        "market_as_of_session": packet["market_as_of_session"],
        "quality_status": packet["quality_status"],
        "quality_issues": packet.get("quality_issues", []),
        "authority": packet["authority"],
        "execution_permission": packet["execution_permission"],
        "advisory_blocks": sorted(packet.get("advisory_context", {})),
        "sector_routes": {
            direction: len(routes)
            for direction, routes in packet.get("sector_routing", {}).items()
        },
        "unverified_metrics": packet["unverified_metrics"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
