"""Configuration registry CLI.

  python -m avshunter.config check
  python -m avshunter.config lock
  python -m avshunter.config resolve --session 2026-09-17
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import sys

from .adapters import DEFAULT_REGISTRY_DIR, load_registry, update_lock
from .model import ConfigError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m avshunter.config")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate documents, history and lock")
    sub.add_parser("lock", help="append hashes for new entries to LOCK.json")
    resolve = sub.add_parser("resolve", help="print the snapshot for a session")
    resolve.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            registry = load_registry(DEFAULT_REGISTRY_DIR)
            print(f"OK: {len(registry.entries())} entries, {len(registry.keys)} keys")
        elif args.command == "lock":
            manifest = update_lock(DEFAULT_REGISTRY_DIR)
            print(f"LOCK updated: {len(manifest)} entries")
        else:
            snapshot = load_registry(DEFAULT_REGISTRY_DIR).resolve(date.fromisoformat(args.session))
            print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    except ConfigError as error:
        print(f"CONFIG ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
