"""Explicit one-job provider runner guarded by a disabled release contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from ..adapters.anthropic_http import AnthropicHTTP
from ..adapters.jobs import JobStore
from ..adapters.lab_reports import AnalystReports
from ..domain import ContractError
from .activation import ControlledProviderRuntime, load_provider_release
from .avshunter_source import AvshunterSourceBridge
from .coordinator import Worker3Coordinator


def _confined(root: Path, value: str) -> Path:
    approved = (root / "data" / "worker3").resolve()
    path = Path(value).resolve()
    if not path.is_relative_to(approved):
        raise ContractError("Worker 3 runtime files must remain inside data/worker3")
    return path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    data = root / "data" / "worker3"
    parser = argparse.ArgumentParser(description="Activate and execute one governed Worker 3 job")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--operator-approval-id", required=True)
    parser.add_argument("--budget-microusd", required=True, type=int)
    parser.add_argument("--database", default=str(data / "worker3_jobs.sqlite"))
    parser.add_argument("--reports", default=str(data / "analyst_reports.sqlite"))
    parser.add_argument(
        "--release",
        default=str(root / "contracts" / "worker3_provider_release_v1.json"),
    )
    args = parser.parse_args(argv)
    database = _confined(root, args.database)
    reports_path = _confined(root, args.reports)
    release = load_provider_release(args.release)
    # This fails before credentials or transport are touched while the installed
    # release remains disabled.
    if not release.enabled:
        raise ContractError("provider release is installed but disabled")
    store = JobStore(database, budget_microusd=args.budget_microusd)
    reports = AnalystReports(reports_path)
    try:
        coordinator = Worker3Coordinator(
            AvshunterSourceBridge(root), store,
            root / "contracts" / "worker3_integration_v1.json",
        )
        runtime = ControlledProviderRuntime(coordinator, store, reports, args.release)
        runtime.activate(
            (args.job_id,), operator_approval_id=args.operator_approval_id,
            now=time.time(),
        )
        transport = AnthropicHTTP(
            enabled=True,
            max_calls=release.max_calls_per_process,
            max_input_bytes=release.max_input_bytes,
            max_output_tokens=release.max_output_tokens,
        )
        result = runtime.execute(args.job_id, transport=transport, clock=time.time)
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        reports.close()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
