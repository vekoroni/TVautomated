from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lab_batch import run_lab_batch


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read the latest Intelligence Lab run and launch ticker workflows"
    )
    parser.add_argument("--pipeline-outputs", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--invocation-id", required=True)
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--execute-shadow-batch", action="store_true")
    parser.add_argument("--capture-webull", action="store_true")
    parser.add_argument("--confirm-attended-shadow-capture", action="store_true")
    parser.add_argument("--run-live-interpreter", action="store_true")
    parser.add_argument("--confirm-shadow-live-provider", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--main-max-tokens", type=int)
    parser.add_argument("--story-max-tokens", type=int, default=12000)
    parser.add_argument("--no-web-search", action="store_true")
    args = parser.parse_args(argv)
    if args.capture_webull and not args.execute_shadow_batch:
        parser.error("--capture-webull requires --execute-shadow-batch")
    if args.capture_webull and not args.confirm_attended_shadow_capture:
        parser.error(
            "--capture-webull requires --confirm-attended-shadow-capture"
        )
    if args.run_live_interpreter and not args.execute_shadow_batch:
        parser.error("--run-live-interpreter requires --execute-shadow-batch")
    if args.run_live_interpreter and not args.confirm_shadow_live_provider:
        parser.error(
            "--run-live-interpreter requires --confirm-shadow-live-provider"
        )
    capture_runner = None
    if args.capture_webull:
        from pipeline_interpreter.capture_v1.attended_workflow import (
            run_attended_capture,
        )

        def capture_runner(ticker: str, ticker_root: Path):
            return run_attended_capture(
                ticker=ticker,
                output_directory=ticker_root / f"{args.invocation_id}-capture",
                automatic_ticker_acceptance=True,
                chart_already_open=True,
            )
    shadow_provider = None
    if args.run_live_interpreter:
        from .live_provider import create_live_shadow_provider

        shadow_provider = create_live_shadow_provider(
            model=args.model,
            main_max_tokens=args.main_max_tokens,
            story_max_tokens=args.story_max_tokens,
            use_web_search=not args.no_web_search,
        )
    try:
        state_path = run_lab_batch(
            pipeline_outputs=args.pipeline_outputs,
            staging_root=args.staging_root,
            output_directory=args.output_directory,
            invocation_id=args.invocation_id,
            max_candidates=args.max_candidates,
            execute_shadow=args.execute_shadow_batch,
            capture_runner=capture_runner,
            shadow_provider=shadow_provider,
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
            "production_charts_touched": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": state["status"], "mode": state["mode"],
        "run_id": state["run_id"],
        "candidate_count": len(state["candidates"]),
        "stopped_count": len(state["stopped"]),
        "candidates": [item["ticker"] for item in state["candidates"]],
        "go_no_go": state.get("go_no_go"), "state": str(state_path),
        "published": False, "production_charts_touched": False,
    }, sort_keys=True))
    return 0 if state["status"] in {"planned", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

