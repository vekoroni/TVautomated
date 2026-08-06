"""Interactive shadow CLI for direct bottom-bar timeframe selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .navigation import FULL_CHART_INTERVAL_POINTS, select_bottom_timeframe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a Webull chart timeframe")
    parser.add_argument(
        "--timeframe", required=True, choices=tuple(FULL_CHART_INTERVAL_POINTS)
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--confirm-full-chart-layout", action="store_true",
        help="Required acknowledgement that Webull is in the mapped full-chart layout",
    )
    args = parser.parse_args(argv)
    if not args.confirm_full_chart_layout:
        parser.error("--confirm-full-chart-layout is required")
    windows = tuple(
        item for item in WindowsShadowBackend().discover("Webull") if item.visible
    )
    if len(windows) != 1:
        print(json.dumps({
            "status": "stopped",
            "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}",
            "pipeline_published": False,
        }))
        return 2
    image, manifest = select_bottom_timeframe(
        window=windows[0],
        timeframe=args.timeframe,
        output_directory=args.output_directory,
    )
    print(json.dumps({
        "status": "selected_for_visual_review",
        "timeframe": args.timeframe,
        "diagnostic_image": str(image),
        "manifest": str(manifest),
        "pipeline_published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
