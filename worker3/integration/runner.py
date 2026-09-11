"""Explicit PREPARE_ONLY command; never dispatches a provider request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from ..adapters.jobs import JobStore
from ..domain import ContractError
from .avshunter_source import AvshunterSourceBridge
from .coordinator import Worker3Coordinator


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Prepare durable advisory Worker 3 jobs")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ticker", action="append", dest="tickers",
                        help="Exact uppercase ticker; repeat for an explicit worklist")
    parser.add_argument(
        "--previous-assessment", action="append", default=[],
        metavar="TICKER=ASSESSMENT_ID",
        help="Create a refresh job using this exact prior assessment; repeat per ticker",
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--budget-microusd", required=True, type=int)
    parser.add_argument("--call-ceiling-microusd", required=True, type=int)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--max-input-bytes", type=int, default=500000)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--database",
        default=str(root / "data" / "worker3" / "worker3_jobs.sqlite"),
    )
    args = parser.parse_args(argv)
    previous = {}
    for item in args.previous_assessment:
        ticker, separator, assessment_id = item.partition("=")
        if not separator or ticker in previous:
            raise ContractError(
                "previous assessments require unique TICKER=ASSESSMENT_ID values"
            )
        previous[ticker] = assessment_id
    database = Path(args.database).resolve()
    approved = (root / "data" / "worker3").resolve()
    if not database.is_relative_to(approved):
        raise ContractError("Worker 3 database must remain inside data/worker3")
    database.parent.mkdir(parents=True, exist_ok=True)
    store = JobStore(database, budget_microusd=args.budget_microusd)
    try:
        coordinator = Worker3Coordinator(
            AvshunterSourceBridge(root),
            store,
            root / "contracts" / "worker3_integration_v1.json",
        )
        result = coordinator.prepare_run(
            args.run_id,
            provider=args.provider,
            model=args.model,
            now=time.time(),
            tickers=tuple(args.tickers) if args.tickers is not None else None,
            previous_assessment_ids=previous or None,
            call_ceiling_microusd=args.call_ceiling_microusd,
            max_output_tokens=args.max_output_tokens,
            max_input_bytes=args.max_input_bytes,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result.summary(), sort_keys=True))
        return 0 if result.summary()["jobs_prepared"] else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
