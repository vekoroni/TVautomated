"""Check a US Money Index packet against the pipeline's own contract before the Evening (ACK 8 Oct 2026).

Usage:  venv\\Scripts\\python.exe scripts\\validate_us_money_index.py [path]
Default path: dropbox\\macro\\avshunter_us_money_index.json. Read-only. Exit 0 = accepted, 1 = refused (reason printed).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.us_money_index_contract import (  # noqa: E402
    USMoneyIndexValidationError, load_us_money_index_sidecar,
)

FLAGS = ("regime_change_since_monday", "monetisation_change_since_monday", "risk_off_transition")


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "dropbox" / "macro" / "avshunter_us_money_index.json"
    try:
        packet = load_us_money_index_sidecar(path)
    except (USMoneyIndexValidationError, ValueError, OSError) as error:
        print(f"REFUSED {path.name}: {error}")
        return 1
    state = packet.get("state") or {}
    print(f"ACCEPTED {path.name}: packet {packet.get('packet_id')} quality {packet.get('quality_status')}")
    for flag in FLAGS:
        print(f"  {flag}={state.get(flag)} ({state.get(flag + '_basis', 'BOOLEAN')})")
    for issue in packet.get("quality_issues") or []:
        print(f"  note: {issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
