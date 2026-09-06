"""Interactive-only CLI for mapping allowlisted Webull controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .navigation import map_timeframe_menu


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map Webull read-only controls")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--confirm-navigation-shadow",
        action="store_true",
        help="Required acknowledgement that the timeframe menu will be opened",
    )
    args = parser.parse_args(argv)
    if not args.confirm_navigation_shadow:
        parser.error("--confirm-navigation-shadow is required")
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
    image, manifest = map_timeframe_menu(
        window=windows[0],
        output_directory=args.output_directory,
    )
    print(json.dumps({
        "status": "mapped",
        "diagnostic_image": str(image),
        "manifest": str(manifest),
        "pipeline_published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

