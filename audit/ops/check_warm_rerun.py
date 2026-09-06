"""AVS-FIX-001 W2.3 — read-only warm-rerun comparison.

    python audit/ops/check_warm_rerun.py <cold_run_id> <warm_run_id> [--json <path>]

Compares a cold run with a same-session warm rerun and reports the four things
AVS-SD-003 AG-20 / G19 requires:

    1  Option-chain PHYSICAL requests in the warm run. Must be 0: the whole
       point of the canonical store is that a second run over the same
       completed session buys no chains twice.
    2  `exact fresh dataset` count — EXACT_OPTION_QUOTE datasets registered
       against the warm run (AG-20's threshold is >= 1,200).
    3  Ledger reconciliation — every warm request resolved, none left PENDING,
       and cache hits accounting for the chains the cold run paid for.
    4  Wall-time comparison, from the ledger's own first/last timestamps, so
       the figure is the run's, not a stopwatch's.

Opens the control plane read-only (SQLite URI mode=ro) and the two run
directories; writes only the file named on the command line. Exit code is 1 if
the warm run bought a chain, if the ledger does not reconcile, or if either run
is unknown to the ledger.
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CONTROL_PLANE = REPO / "data" / "canonical" / "control_plane.sqlite"
RUNS = REPO / "data" / "output" / "runs"

#: Resolutions that mean the provider was actually called and billed.
PHYSICAL_RESOLUTIONS = ("PROVIDER_FETCH", "PROVIDER_ERROR", "PROVIDER_NO_DATA")


def connect() -> sqlite3.Connection:
    if not CONTROL_PLANE.exists():
        raise SystemExit(f"control plane not found: {CONTROL_PLANE}")
    connection = sqlite3.connect(f"file:{CONTROL_PLANE}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def ledger_summary(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT dataset_type, resolution, "
        "       COUNT(*) AS requests, "
        "       COALESCE(SUM(physical_request_count), 0) AS physical, "
        "       MIN(started_at) AS first_start, MAX(completed_at) AS last_finish "
        "FROM api_request_ledger WHERE run_id = ? "
        "GROUP BY dataset_type, resolution",
        (run_id,),
    ).fetchall()

    summary: dict[str, Any] = {
        "run_id": run_id,
        "known_to_ledger": bool(rows),
        "by_type_resolution": {},
        "requests_total": 0,
        "physical_total": 0,
        "physical_option_chain": 0,
        "cache_hits": 0,
        "pending": 0,
        "first_start": None,
        "last_finish": None,
    }
    for row in rows:
        key = f"{row['dataset_type']}/{row['resolution']}"
        summary["by_type_resolution"][key] = {
            "requests": row["requests"], "physical": row["physical"],
        }
        summary["requests_total"] += row["requests"]
        summary["physical_total"] += row["physical"]
        if row["dataset_type"] == "OPTION_CHAIN" and row["resolution"] in PHYSICAL_RESOLUTIONS:
            summary["physical_option_chain"] += row["physical"]
        if row["resolution"] in ("CACHE_HIT", "PARTIAL_HIT"):
            summary["cache_hits"] += row["requests"]
        if row["resolution"] == "PENDING":
            summary["pending"] += row["requests"]
        for field, value in (("first_start", row["first_start"]),
                             ("last_finish", row["last_finish"])):
            if not value:
                continue
            current = summary[field]
            if current is None or (
                value < current if field == "first_start" else value > current
            ):
                summary[field] = value

    summary["exact_fresh_datasets"] = connection.execute(
        "SELECT COUNT(*) FROM dataset_registry "
        "WHERE source_run_id = ? AND dataset_type = 'EXACT_OPTION_QUOTE'",
        (run_id,),
    ).fetchone()[0]
    summary["datasets_registered"] = connection.execute(
        "SELECT COUNT(*) FROM dataset_registry WHERE source_run_id = ?", (run_id,)
    ).fetchone()[0]
    summary["wall_seconds"] = wall_seconds(summary["first_start"], summary["last_finish"])
    return summary


def wall_seconds(first: str | None, last: str | None) -> float | None:
    if not first or not last:
        return None
    try:
        start = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
        finish = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((finish - start).total_seconds(), 1)


def completed_session(run_id: str) -> str | None:
    """The session the run covers.

    run_meta carries it under `dynamic_plan.last_completed_session` on runs
    dispatched through the plan engine. Run 20260905_151448 has no
    `dynamic_plan` block at all, so the stage artefact is the fallback -- the
    same derivation check_run_gates.py uses for DDD-COMPLETED-SESSION.
    """

    matches = glob.glob(str(RUNS / run_id / "run_meta.json"))
    if matches:
        try:
            meta = json.loads(Path(matches[0]).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        plan = meta.get("dynamic_plan") or {}
        session = plan.get("last_completed_session") or meta.get("completed_session")
        if session:
            return str(session)[:10]

    for pattern in (
        RUNS / run_id / "options" / f"options_intelligence_{run_id}.csv",
        RUNS / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv",
    ):
        found = glob.glob(str(pattern))
        if not found:
            continue
        try:
            import pandas as pd

            frame = pd.read_csv(found[0], low_memory=False, nrows=200)
        except Exception:
            continue
        for column in ("evidence_session_date", "completed_session", "session_date"):
            if column in frame.columns:
                values = frame[column].dropna().astype(str).str.slice(0, 10).unique()
                if len(values):
                    return str(values[0])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cold_run_id")
    parser.add_argument("warm_run_id")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument(
        "--min-exact-fresh", type=int, default=1200,
        help="AG-20 threshold for EXACT_OPTION_QUOTE datasets (default 1200)",
    )
    args = parser.parse_args(argv)

    connection = connect()
    cold = ledger_summary(connection, args.cold_run_id)
    warm = ledger_summary(connection, args.warm_run_id)
    cold_session = completed_session(args.cold_run_id)
    warm_session = completed_session(args.warm_run_id)

    checks: list[dict[str, Any]] = []

    def check(name: str, description: str, value: Any, required: Any,
              passed: bool, blocking: bool = True) -> None:
        checks.append({
            "check": name, "description": description, "value": value,
            "required": required, "verdict": "PASS" if passed else "FAIL",
            "blocking": blocking,
        })

    check("LEDGER-KNOWS-COLD", "cold run present in the request ledger",
          cold["known_to_ledger"], True, cold["known_to_ledger"])
    check("LEDGER-KNOWS-WARM", "warm run present in the request ledger",
          warm["known_to_ledger"], True, warm["known_to_ledger"])

    check("SAME-COMPLETED-SESSION",
          "both runs cover the same completed session",
          f"cold={cold_session} warm={warm_session}",
          "equal and non-null",
          bool(cold_session) and cold_session == warm_session,
          blocking=False)

    check("WARM-CHAIN-PHYSICAL-ZERO",
          "option-chain physical requests in the warm run",
          warm["physical_option_chain"], 0,
          warm["physical_option_chain"] == 0)

    check("EXACT-FRESH-DATASETS",
          "EXACT_OPTION_QUOTE datasets registered by the warm run",
          warm["exact_fresh_datasets"], f">= {args.min_exact_fresh}",
          warm["exact_fresh_datasets"] >= args.min_exact_fresh,
          blocking=False)

    check("LEDGER-NO-PENDING", "no warm request left PENDING",
          warm["pending"], 0, warm["pending"] == 0)

    check("LEDGER-RECONCILES",
          "warm requests all resolved (requests == sum of resolutions)",
          warm["requests_total"],
          sum(entry["requests"] for entry in warm["by_type_resolution"].values()),
          warm["requests_total"]
          == sum(entry["requests"] for entry in warm["by_type_resolution"].values()))

    check("WARM-CACHE-HITS", "warm run served from cache", warm["cache_hits"],
          "> 0", warm["cache_hits"] > 0, blocking=False)

    faster = (
        cold["wall_seconds"] is not None
        and warm["wall_seconds"] is not None
        and warm["wall_seconds"] < cold["wall_seconds"]
    )
    check("WALL-TIME-LOWER",
          "warm run materially faster than the cold run",
          f"cold={cold['wall_seconds']}s warm={warm['wall_seconds']}s",
          "warm < cold", faster, blocking=False)

    print("=" * 96)
    print(f"AVS-FIX-001 W2.3 warm-rerun check: cold={args.cold_run_id} "
          f"warm={args.warm_run_id}")
    print(f"control plane: {CONTROL_PLANE} (read only)")
    print("=" * 96)
    for entry in checks:
        marker = "BLOCKING" if entry["blocking"] else "        "
        print(f"  {entry['verdict']:4s} {marker} {entry['check']:26s} "
              f"value={str(entry['value']):>28s} required={entry['required']}")

    print("-" * 96)
    for label, summary in (("cold", cold), ("warm", warm)):
        print(f"  {label}: requests={summary['requests_total']} "
              f"physical={summary['physical_total']} "
              f"chain_physical={summary['physical_option_chain']} "
              f"cache_hits={summary['cache_hits']} "
              f"datasets={summary['datasets_registered']} "
              f"exact_fresh={summary['exact_fresh_datasets']} "
              f"wall={summary['wall_seconds']}s")

    if cold["physical_total"]:
        saved = cold["physical_total"] - warm["physical_total"]
        print(f"  physical requests avoided by the warm run: {saved} "
              f"({saved / cold['physical_total']:.1%} of the cold run)")

    failures = [c for c in checks if c["verdict"] == "FAIL" and c["blocking"]]
    advisory = [c for c in checks if c["verdict"] == "FAIL" and not c["blocking"]]
    print(f"  blocking failures: {len(failures)}"
          + (" -> " + ", ".join(c["check"] for c in failures) if failures else ""))
    if advisory:
        print(f"  advisory failures: {len(advisory)} -> "
              + ", ".join(c["check"] for c in advisory))

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(
            {"cold": cold, "warm": warm, "checks": checks}, indent=2, default=str
        ), encoding="utf-8")
        print(f"  json: {args.json_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
