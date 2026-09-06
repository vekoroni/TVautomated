"""Explicit-input, shadow-only command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .comparison import compare_legacy_to_shadow
from .compatibility import profile_legacy_artifacts
from .core import interpret_ticker
from .fixture_provider import FixtureResponseProvider
from .legacy_adapter import LegacyInputSpec, build_request_from_legacy
from .metrics import evaluate_acceptance, load_trial_metrics
from .renderers import publish_complete_shadow_artifacts
from .replay import read_request_fixture, write_request_fixture
from .serialization import to_plain
from .shadow import publish_shadow_result
from .trial import run_shadow_trial


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AVSHUNTER Pipeline Interpreter automation v2 (SHADOW ONLY)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-request")
    build.add_argument("--ticker", required=True)
    build.add_argument("--run-id", required=True)
    build.add_argument("--invocation-id", required=True)
    build.add_argument("--as-of", required=True)
    build.add_argument("--pipeline-csv", required=True)
    build.add_argument("--lab-csv")
    build.add_argument("--option-csv", action="append", default=[])
    build.add_argument("--chart-root", action="append", default=[])
    build.add_argument("--macro-json")
    build.add_argument("--trader-note", default="")
    build.add_argument("--require-lab", action="store_true")
    build.add_argument("--max-age-hours", type=float)
    build.add_argument("--output", required=True)

    run = sub.add_parser("run-fixture")
    run.add_argument("--request", required=True)
    run.add_argument("--main-response", required=True)
    run.add_argument("--story-response", required=True)
    run.add_argument("--shadow-root", required=True)

    live = sub.add_parser("run-live-shadow")
    live.add_argument("--request", required=True)
    live.add_argument("--shadow-root", required=True)
    live.add_argument("--model")
    live.add_argument("--main-max-tokens", type=int)
    live.add_argument("--story-max-tokens", type=int, default=12000)
    live.add_argument("--no-web-search", action="store_true")
    live.add_argument(
        "--confirm-shadow-live-provider",
        action="store_true",
        help="Required acknowledgement that this makes billable provider calls.",
    )

    compare = sub.add_parser("compare")
    compare.add_argument("--ticker", required=True)
    compare.add_argument("--legacy-raw", required=True)
    compare.add_argument("--legacy-story", required=True)
    compare.add_argument("--legacy-html", required=True)
    compare.add_argument("--shadow-dir", required=True)
    compare.add_argument("--output")

    acceptance = sub.add_parser("acceptance")
    acceptance.add_argument("--metrics-root", required=True)
    acceptance.add_argument("--output")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    if args.command == "build-request":
        request = build_request_from_legacy(
            LegacyInputSpec(
                ticker=args.ticker,
                run_id=args.run_id,
                invocation_id=args.invocation_id,
                as_of=args.as_of,
                pipeline_csv=args.pipeline_csv,
                lab_csv=args.lab_csv,
                option_csvs=tuple(args.option_csv),
                chart_roots=tuple(args.chart_root),
                macro_json=args.macro_json,
                trader_note=args.trader_note,
                require_lab=args.require_lab,
                max_age_hours=args.max_age_hours,
            )
        )
        output = write_request_fixture(request, args.output)
        print(json.dumps({"shadow": True, "request": str(output)}, sort_keys=True))
        return 0

    if args.command == "run-fixture":
        request = read_request_fixture(args.request)
        provider = FixtureResponseProvider(
            Path(args.main_response).read_text(encoding="utf-8-sig"),
            Path(args.story_response).read_text(encoding="utf-8-sig"),
        )
        result = interpret_ticker(request, provider)
        if result.analysis is not None:
            output = publish_complete_shadow_artifacts(result, args.shadow_root)
        else:
            output = publish_shadow_result(result, args.shadow_root)
        print(
            json.dumps(
                {
                    "shadow": True,
                    "status": result.status.value,
                    "effective_verdict": result.effective_verdict,
                    "output": str(output),
                },
                sort_keys=True,
            )
        )
        return 2 if result.status.value in {"degraded", "failed"} else 0

    if args.command == "run-live-shadow":
        if not args.confirm_shadow_live_provider:
            raise SystemExit(
                "--confirm-shadow-live-provider is required for live provider calls"
            )
        from .live_provider import create_live_shadow_provider

        request = read_request_fixture(args.request)
        checkpoint_dir = (
            Path(args.shadow_root).resolve()
            / "_checkpoints"
            / request.run_id
            / request.ticker
            / request.invocation_id
        )

        def record_stage(stage: str, response: str) -> None:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            (checkpoint_dir / f"{stage}_response.txt").write_text(
                response, encoding="utf-8"
            )

        trial = run_shadow_trial(
            request=request,
            provider=create_live_shadow_provider(
                model=args.model,
                main_max_tokens=args.main_max_tokens,
                story_max_tokens=args.story_max_tokens,
                use_web_search=not args.no_web_search,
                stage_recorder=record_stage,
            ),
            shadow_root=args.shadow_root,
        )
        print(json.dumps(to_plain(trial), indent=2, sort_keys=True))
        return 2 if trial.metric.status in {"degraded", "failed"} else 0

    if args.command == "acceptance":
        report = evaluate_acceptance(load_trial_metrics(args.metrics_root))
        rendered = json.dumps(to_plain(report), indent=2, sort_keys=True)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        print(rendered)
        return 0 if report.accepted else 4

    legacy = profile_legacy_artifacts(
        ticker=args.ticker,
        raw_response=args.legacy_raw,
        raw_story=args.legacy_story,
        html=args.legacy_html,
    )
    report = compare_legacy_to_shadow(legacy, args.shadow_dir)
    payload = to_plain(report)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report.passed else 3


if __name__ == "__main__":
    sys.exit(main())

