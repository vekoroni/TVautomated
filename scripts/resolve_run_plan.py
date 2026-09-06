"""Resolve a dynamic AVSHUNTER RunPlan without calling any provider."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.run_planning import RequestedAction
from canonical_data.run_plan import resolve_run_plan
from canonical_data.run_plan_store import RunPlanStore, write_plan_atomic


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=[item.value for item in RequestedAction], default="AUTO")
    parser.add_argument("--as-of-utc", required=True, type=_instant)
    parser.add_argument("--evidence-cutoff-utc", type=_instant)
    parser.add_argument("--existing-thesis-id")
    parser.add_argument("--existing-thesis-session", type=date.fromisoformat)
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--provider-session-finalised", action="store_true")
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--persist-store", type=Path)
    arguments = parser.parse_args()
    plan = resolve_run_plan(
        requested_action=arguments.action,
        as_of_utc=arguments.as_of_utc,
        evidence_cutoff_utc=arguments.evidence_cutoff_utc,
        existing_thesis_id=arguments.existing_thesis_id,
        existing_thesis_session=arguments.existing_thesis_session,
        authorised_tickers=arguments.ticker,
        provider_session_finalised=arguments.provider_session_finalised,
        pipeline_run_id=arguments.pipeline_run_id,
    )
    if arguments.output:
        write_plan_atomic(plan, arguments.output)
    if arguments.persist_store:
        RunPlanStore(arguments.persist_store).persist(plan)
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
