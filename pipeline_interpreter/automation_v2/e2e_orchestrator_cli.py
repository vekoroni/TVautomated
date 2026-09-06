from __future__ import annotations

import argparse
import json
from pathlib import Path

from .e2e_orchestrator import run_e2e_workflow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Resume or run the post-capture ticker workflow"
    )
    parser.add_argument("ticker")
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--pipeline-outputs", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--invocation-id", required=True)
    parser.add_argument("--confirm-shadow-e2e", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_shadow_e2e:
        parser.error("--confirm-shadow-e2e is required")
    try:
        state_path = run_e2e_workflow(
            ticker=args.ticker,
            staging_root=args.staging_root,
            pipeline_outputs=args.pipeline_outputs,
            output_directory=args.output_directory,
            invocation_id=args.invocation_id,
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc),
            "production_charts_touched": False, "published": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": state["status"], "ticker": state["ticker"],
        "go_no_go": state.get("go_no_go"), "state": str(state_path),
        "steps": state["steps"], "production_charts_touched": False,
        "published": False,
    }, sort_keys=True))
    return 0 if state["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

