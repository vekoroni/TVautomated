"""Interactive shadow CLI for Webull ticker switching."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .navigation import switch_ticker_for_visual_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Switch Webull ticker in shadow mode")
    parser.add_argument("ticker")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-ticker-navigation-shadow", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_ticker_navigation_shadow:
        parser.error("--confirm-ticker-navigation-shadow is required")
    windows = tuple(
        item for item in WindowsShadowBackend().discover("Webull") if item.visible
    )
    if len(windows) != 1:
        print(json.dumps({"status": "stopped", "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}"}))
        return 2
    try:
        image, manifest = switch_ticker_for_visual_review(
            window=windows[0], ticker=args.ticker,
            output_directory=args.output_directory,
        )
    except Exception as exc:
        print(json.dumps({"status": "stopped", "finding": str(exc), "published": False}))
        return 2
    print(json.dumps({
        "status": "switched_for_visual_review", "ticker": args.ticker.upper(),
        "diagnostic_image": str(image), "manifest": str(manifest),
        "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

