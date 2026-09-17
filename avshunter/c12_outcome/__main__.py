"""Outcome scorer CLI.

  python -m avshunter.c12_outcome ingest
  python -m avshunter.c12_outcome score  [--as-of YYYY-MM-DD]   (default: latest complete price session)
  python -m avshunter.c12_outcome conditions                  (analysis labels; never used by decisions)
  python -m avshunter.c12_outcome base-rate [--as-of YYYY-MM-DD]
  python -m avshunter.c12_outcome report [--as-of YYYY-MM-DD]
  python -m avshunter.c12_outcome all    [--as-of YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

from avshunter.c0_run.adapters.clock import wall_clock_utc
from avshunter.c0_run.clock import build_decision_clock
from avshunter.config import ConfigError
from avshunter.config.adapters import load_registry
from avshunter.shared.xnys_calendar import is_xnys_session

from . import service
from .adapters import prices, storage

REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "data" / "output" / "runs"
REPORTS_DIR = REPO / "Enhancements" / "outcomes"


def _config_session(clock) -> date:
    if clock.market_session is not None:
        return clock.market_session
    return clock.evidence_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m avshunter.c12_outcome")
    parser.add_argument("command", choices=["ingest", "score", "conditions", "base-rate", "report", "all"])
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)
    now = wall_clock_utc()
    clock = build_decision_clock(now)
    try:
        snapshot = load_registry().resolve(_config_session(clock))
        snapshot.get("outcome.window_sessions")
    except ConfigError as error:
        print(f"CONFIG ERROR: {error}", file=sys.stderr)
        return 2
    as_of = date.fromisoformat(args.as_of) if args.as_of else prices.latest_session()
    if not is_xnys_session(as_of) or as_of > clock.evidence_session:
        print(f"as-of {as_of} must be a completed XNYS session (last completed: {clock.evidence_session})", file=sys.stderr)
        return 2
    connection = storage.connect()
    results = {"as_of": as_of.isoformat(), "scorer_version": service.SCORER_VERSION}
    if args.command in ("ingest", "all"):
        results["ingest"] = service.ingest(connection, RUNS_DIR, now)
    if args.command in ("score", "all"):
        results["score"] = service.score(connection, as_of, snapshot, now)
    if args.command in ("conditions", "all"):
        results["conditions"] = service.record_conditions(connection, RUNS_DIR, snapshot, now)
    if args.command in ("base-rate", "all"):
        results["base_rate"] = service.score_base_rates(connection, as_of, snapshot, now)
    if args.command in ("report", "all"):
        results["report"] = str(service.build_report(connection, as_of, snapshot, REPORTS_DIR / as_of.isoformat()))
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
